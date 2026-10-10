use super::*;

fn segment(mapping: &[Extent], position: u64, remaining: usize) -> Result<(u64, usize), String> {
    let i = mapping.partition_point(|e| e.end <= position);
    let e = mapping
        .get(i)
        .filter(|e| e.start <= position && position < e.end)
        .ok_or("MFT 分段存在缺口")?;
    Ok((
        e.disk + position - e.start,
        (e.end - position).min(remaining as u64) as usize,
    ))
}

pub(super) fn dual<R: Read + Seek + Send>(
    readers: [R; 2],
    mapping: &[Extent],
    length: u64,
    sector: usize,
    cancel: &AtomicBool,
    mut consume: impl FnMut(u64, &mut [u8]) -> bool,
) -> (MftBulkStats, Option<String>) {
    const READ_SIZE: usize = BLOCK_SIZE;
    std::thread::scope(|scope| {
        let mut queues = Vec::new();
        let mut workers = Vec::new();
        let mut error = None;
        for (id, mut reader) in readers.into_iter().enumerate() {
            let (free_tx, free_rx) = sync_channel(2);
            let (ready_tx, ready_rx) = sync_channel(1);
            for _ in 0..2 {
                free_tx.send(vec![0u8; READ_SIZE + sector]).unwrap();
            }
            let worker = std::thread::Builder::new()
                .name(format!("mft-read-{id}"))
                .spawn_scoped(scope, move || {
                    let mut stats = MftBulkStats::default();
                    let mut offset = id as u64 * READ_SIZE as u64;
                    while offset < length && !cancel.load(Ordering::Relaxed) {
                        let Ok(mut storage) = free_rx.recv() else {
                            break;
                        };
                        let alignment = (sector - storage.as_ptr() as usize % sector) % sector;
                        let amount = (length - offset).min(READ_SIZE as u64) as usize;
                        let started = Instant::now();
                        let result = (|| -> Result<(), String> {
                            let mut filled = 0;
                            while filled < amount {
                                if cancel.load(Ordering::Relaxed) {
                                    return Err("已取消读取".into());
                                }
                                let (disk, count) =
                                    segment(mapping, offset + filled as u64, amount - filled)?;
                                reader
                                    .seek(SeekFrom::Start(disk))
                                    .map_err(|e| e.to_string())?;
                                stats.read_calls += 1;
                                let n = reader
                                    .read(
                                        &mut storage
                                            [alignment + filled..alignment + filled + count],
                                    )
                                    .map_err(|e| e.to_string())?;
                                stats.bytes_read += n as u64;
                                if n != count {
                                    return Err("原始 MFT 批量读取长度不足".into());
                                }
                                filled += n;
                            }
                            Ok(())
                        })();
                        stats.read_ms += started.elapsed().as_secs_f64() * 1000.0;
                        if let Err(e) = result {
                            let _ = ready_tx.send(Err(e));
                            break;
                        }
                        if ready_tx.send(Ok((storage, alignment, amount))).is_err() {
                            break;
                        }
                        offset += 2 * READ_SIZE as u64;
                    }
                    stats
                });
            match worker {
                Ok(worker) => {
                    workers.push(worker);
                    queues.push((free_tx, ready_rx));
                }
                Err(e) => {
                    error = Some(format!("无法启动读取线程: {e}"));
                    break;
                }
            }
        }
        if error.is_none() {
            let mut offset = 0;
            while offset < length && !cancel.load(Ordering::Relaxed) {
                let id = (offset / READ_SIZE as u64 % 2) as usize;
                match queues[id].1.recv() {
                    Ok(Ok((mut storage, alignment, amount))) => {
                        if !consume(offset, &mut storage[alignment..alignment + amount]) {
                            break;
                        }
                        let _ = queues[id].0.send(storage);
                        offset += amount as u64;
                    }
                    Ok(Err(e)) => {
                        error = Some(e);
                        break;
                    }
                    Err(_) => {
                        error = Some("MFT 读取线程提前退出".into());
                        break;
                    }
                }
            }
        }
        drop(queues);
        let mut stats = MftBulkStats {
            block_bytes: READ_SIZE as u64,
            prefetch_buffers: 4,
            ..Default::default()
        };
        for worker in workers {
            match worker.join() {
                Ok(s) => {
                    stats.bytes_read += s.bytes_read;
                    stats.read_calls += s.read_calls;
                    stats.read_ms += s.read_ms;
                }
                Err(_) => error = Some("MFT 读取线程异常退出".into()),
            }
        }
        (stats, error)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn dual_reads_fragmented_blocks_in_order_and_reports_short_reads() {
        let disk: Vec<u8> = (0..BLOCK_SIZE * 21)
            .map(|i| (i / 512 % 251) as u8)
            .collect();
        let mapping = [
            Extent {
                start: 0,
                end: 512,
                disk: (BLOCK_SIZE * 20) as u64,
            },
            Extent {
                start: 512,
                end: (BLOCK_SIZE * 20 + 512) as u64,
                disk: 0,
            },
        ];
        let cancel = AtomicBool::new(false);
        let mut observed = Vec::new();
        struct DelayedReader<'a>(Cursor<&'a [u8]>);
        impl Read for DelayedReader<'_> {
            fn read(&mut self, bytes: &mut [u8]) -> std::io::Result<usize> {
                if self.0.position() == (BLOCK_SIZE * 20) as u64 {
                    std::thread::sleep(std::time::Duration::from_millis(20));
                }
                self.0.read(bytes)
            }
        }
        impl Seek for DelayedReader<'_> {
            fn seek(&mut self, offset: SeekFrom) -> std::io::Result<u64> {
                self.0.seek(offset)
            }
        }
        let (stats, error) = dual(
            [
                DelayedReader(Cursor::new(&disk)),
                DelayedReader(Cursor::new(&disk)),
            ],
            &mapping,
            (BLOCK_SIZE * 20 + 512) as u64,
            512,
            &cancel,
            |offset, bytes| {
                assert_eq!(offset, observed.len() as u64);
                observed.extend_from_slice(bytes);
                true
            },
        );
        assert!(error.is_none(), "{error:?}");
        assert_eq!(stats.bytes_read, observed.len() as u64);
        assert_eq!(
            &observed[..512],
            &disk[BLOCK_SIZE * 20..BLOCK_SIZE * 20 + 512]
        );
        assert_eq!(&observed[512..], &disk[..BLOCK_SIZE * 20]);
        let (_, error) = dual(
            [Cursor::new(&disk[..512]), Cursor::new(&disk[..512])],
            &mapping,
            BLOCK_SIZE as u64,
            512,
            &cancel,
            |_, _| panic!("short block delivered"),
        );
        assert!(error.is_some());
        for set_cancel in [false, true] {
            let mut calls = 0;
            let _ = dual(
                [Cursor::new(&disk), Cursor::new(&disk)],
                &mapping,
                (BLOCK_SIZE * 20) as u64,
                512,
                &cancel,
                |_, _| {
                    calls += 1;
                    cancel.store(set_cancel, Ordering::Relaxed);
                    false
                },
            );
            assert_eq!(calls, 1);
        }
    }
}
