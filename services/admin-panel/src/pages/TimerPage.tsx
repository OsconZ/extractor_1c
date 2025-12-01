import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Hero } from '../components/Hero';
import { DispatchResponse } from '../types/api';
import { downloadJson } from '../utils/download';

interface TimerPageProps {
    baseUrl: string;
}

export function TimerPage({ baseUrl }: TimerPageProps) {
    const [file, setFile] = useState<File | null>(null);
    const [status, setStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
    const [elapsed, setElapsed] = useState(0);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [result, setResult] = useState<DispatchResponse | null>(null);

    const controllerRef = useRef<AbortController | null>(null);
    const rafRef = useRef<number | null>(null);
    const startedAtRef = useRef<number | null>(null);
    const timeRef = useRef<HTMLDivElement | null>(null);

    const formattedTime = useMemo(() => {
        const totalSeconds = Math.floor(elapsed / 1000);
        const minutes = Math.floor(totalSeconds / 60)
            .toString()
            .padStart(2, '0');
        const seconds = (totalSeconds % 60).toString().padStart(2, '0');
        const milliseconds = Math.floor(elapsed % 1000)
            .toString()
            .padStart(3, '0');

        return `${minutes}:${seconds}.${milliseconds}`;
    }, [elapsed]);

    useEffect(() => {
        return () => {
            if (controllerRef.current) controllerRef.current.abort();
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
        };
    }, []);

    function formatTime(ms: number): string {
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
        const seconds = (totalSeconds % 60).toString().padStart(2, '0');
        const milliseconds = Math.floor(ms % 1000).toString().padStart(3, '0');
        return `${minutes}:${seconds}.${milliseconds}`;
    }

    const tick = (t: number) => {
        if (!startedAtRef.current) return;
        const ms = t - startedAtRef.current;

        // прямое обновление DOM, без React
        if (timeRef.current) {
            timeRef.current.textContent = formatTime(ms);
        }

        rafRef.current = requestAnimationFrame(tick);
    };

    const startTimer = () => {
        startedAtRef.current = performance.now();
        rafRef.current = requestAnimationFrame(tick);
    };

    const stopTimer = () => {
        if (rafRef.current) cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
    };

    const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();

        if (!file) {
            setErrorMessage('Пожалуйста, выберите файл для отправки в сервисы.');
            return;
        }

        if (controllerRef.current) {
            controllerRef.current.abort();
        }

        setStatus('running');
        setResult(null);
        setErrorMessage(null);
        setElapsed(0);

        startTimer();

        const formData = new FormData();
        formData.append('file', file);

        const controller = new AbortController();
        controllerRef.current = controller;

        try {
            const response = await fetch(`${baseUrl}/api/sections/dispatch`, {
                method: 'POST',
                body: formData,
                signal: controller.signal,
            });

            stopTimer();
            setElapsed(performance.now() - startedAtRef.current!);

            if (!response.ok) {
                const message = await response.text();
                throw new Error(message || 'Не удалось получить ответы от сервисов');
            }

            const json = (await response.json()) as DispatchResponse;
            setResult(json);
            setStatus('done');
        } catch (error) {
            stopTimer();

            if (controller.signal.aborted) {
                return;
            }

            setStatus('error');
            setErrorMessage(error instanceof Error ? error.message : 'Неизвестная ошибка');
        } finally {
            controllerRef.current = null;
        }
    };


    return (
        <div className="page">
            <Hero
                title="Таймер /api/sections/dispatch"
                subtitle="Отправляем файл и следим за временем ответа сервиса. Таймер останавливается сразу после завершения запроса."
            />

            <form className="upload" onSubmit={handleSubmit}>
                <label className="upload__field">
                    <span>Файл договора</span>
                    <input
                        type="file"
                        accept=".pdf,.doc,.docx,.txt,.rtf"
                        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                    />
                </label>

                <button className="upload__button" type="submit" disabled={status === 'running'}>
                    {status === 'running' ? 'Отправка…' : 'Запустить таймер'}
                </button>

                <p className="upload__hint">Страница доступна по адресу /timer и открывается обычной ссылкой.</p>
            </form>

            <section className="timer">
                <div className="timer__meta">
                    <div>
                        <div className="timer__label">Файл</div>
                        <div className="timer__value">{file?.name ?? 'Файл не выбран'}</div>
                    </div>
                    <div>
                        <div className="timer__label">Статус</div>
                        <div className={`timer__status timer__status--${status}`}>
                            {status === 'running' && 'В процессе'}
                            {status === 'done' && 'Готово'}
                            {status === 'error' && 'Ошибка'}
                            {status === 'idle' && 'Ожидание'}
                        </div>
                    </div>
                </div>

                <div className="timer__display">
                    <div
                        className={
                            "clock " + (status === "running" ? "clock--running" : "clock--paused")
                        }
                    >
                        <div className="clock__face">
                            <div className="clock__hand clock__hand--minute" />
                            <div className="clock__hand clock__hand--second" />
                            <div className="clock__center" />
                        </div>
                        <div className="timer__clock" ref={timeRef}>00:00.000</div>

                    </div>
                    <p className="timer__hint">Таймер обновляется пока выполняется запрос к /api/sections/dispatch.</p>
                </div>

                {errorMessage && <div className="alert alert--error">{errorMessage}</div>}

                {result && (
                    <div className="timer__result">
                        <div className="results__header">
                            <h2>Ответ сервиса</h2>
                            <div className="results__actions">
                                <button type="button" onClick={() => setResult(null)}>
                                    Очистить
                                </button>
                                <button type="button" onClick={() => downloadJson(result, 'dispatch.json')}>
                                    Скачать JSON
                                </button>
                            </div>
                        </div>
                        <pre className="results__text">{JSON.stringify(result, null, 2)}</pre>
                    </div>
                )}
            </section>

            <div className="timer__links">
                <a className="link" href="/">
                    Вернуться к панели
                </a>
            </div>
        </div>
    );
}