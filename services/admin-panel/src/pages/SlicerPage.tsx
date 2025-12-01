import React, { useState } from 'react';
import { Hero } from '../components/Hero';
import { SpecificationBlock } from '../components/SpecificationBlock';
import {
  DispatchResponse,
  SpecificationJson,
  SplitResponse,
  SpecificationResponse,
} from '../types/api';
import { downloadJson } from '../utils/download';

interface SlicerPageProps {
  baseUrl: string;
}

export function SlicerPage({ baseUrl }: SlicerPageProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SplitResponse | null>(null);
  const [dispatchFile, setDispatchFile] = useState<File | null>(null);
  const [dispatchLoading, setDispatchLoading] = useState(false);
  const [dispatchError, setDispatchError] = useState<string | null>(null);
  const [dispatchResult, setDispatchResult] = useState<DispatchResponse | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!file) {
      setError('Пожалуйста, выберите файл договора.');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      setLoading(true);
      const sectionsResponse = await fetch(`${baseUrl}/api/sections/split`, {
        method: 'POST',
        body: formData,
      });

      if (!sectionsResponse.ok) {
        const message = await sectionsResponse.text();
        throw new Error(message || 'Не удалось обработать файл');
      }

      const sectionsJson = (await sectionsResponse.json()) as SplitResponse;

      let specJson: SpecificationResponse | null = null;
      try {
        const specResponse = await fetch(`${baseUrl}/api/specification/parse`, {
          method: 'POST',
          body: formData,
        });

        if (specResponse.ok) {
          specJson = (await specResponse.json()) as SpecificationResponse;
        }
      } catch (specError) {
        console.warn('Не удалось получить спецификацию:', specError);
      }

      setResult({ ...sectionsJson, ...(specJson ?? {}) });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Неизвестная ошибка';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleDispatchSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setDispatchError(null);
    setDispatchResult(null);

    if (!dispatchFile) {
      setDispatchError('Пожалуйста, выберите файл для отправки в сервисы.');
      return;
    }

    const formData = new FormData();
    formData.append('file', dispatchFile);

    try {
      setDispatchLoading(true);
      const response = await fetch(`${baseUrl}/api/sections/dispatch`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || 'Не удалось получить ответы от сервисов');
      }

      const json = (await response.json()) as DispatchResponse;
      setDispatchResult(json);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Неизвестная ошибка';
      setDispatchError(message);
    } finally {
      setDispatchLoading(false);
    }
  };

  return (
    <div className="page">
      <Hero
        title="Проверка сервиса нарезки документов"
        subtitle="Подгрузите файл договора, чтобы получить секции part_0 – part_16 и извлечённую спецификацию через отдельный эндпойнт."
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

        <button className="upload__button" type="submit" disabled={loading}>
          {loading ? 'Обработка…' : 'Отправить'}
        </button>
      </form>

      <section className="results">
        <div className="results__header">
          <h2>Отправка секций в сервисы</h2>
          <p className="results__subtitle">
            После разбиения договора данные уходят в несколько сервисов параллельно.
          </p>
        </div>

        <form className="upload" onSubmit={handleDispatchSubmit}>
          <label className="upload__field">
            <span>Файл договора</span>
            <input
              type="file"
              accept=".pdf,.doc,.docx,.txt,.rtf"
              onChange={(event) => setDispatchFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <button className="upload__button" type="submit" disabled={dispatchLoading}>
            {dispatchLoading ? 'Отправка…' : 'Отправить в сервисы'}
          </button>
        </form>
      </section>

      {dispatchError && <div className="alert alert--error">{dispatchError}</div>}

      {error && <div className="alert alert--error">{error}</div>}

      {result && (
        <section className="results">
          <div className="results__header">
            <h2>Результат секционирования</h2>
            <div className="results__actions">
              <button type="button" onClick={() => setResult(null)}>
                Очистить
              </button>
              <button type="button" onClick={() => downloadJson(result, 'sections.json')}>
                Скачать JSON
              </button>
            </div>
          </div>

          <div className="results__grid">
            {Object.entries(result)
              .filter(([key]) => key.startsWith('part_'))
              .map(([key, value]) => (
                <article key={key} className="results__card">
                  <div className="results__title">{key}</div>
                  <pre className="results__text">{typeof value === 'string' ? value || '—' : '—'}</pre>
                </article>
              ))}

            {(() => {
              const specJsonValue = (result as { spec_json?: SpecificationJson | null }).spec_json;
              return specJsonValue ? <SpecificationBlock spec={specJsonValue} /> : null;
            })()}
          </div>
        </section>
      )}

      {dispatchResult && (
        <section className="results">
          <div className="results__header">
            <h2>Ответы сервисов</h2>
            <div className="results__actions">
              <button type="button" onClick={() => setDispatchResult(null)}>
                Очистить
              </button>
              <button type="button" onClick={() => downloadJson(dispatchResult, 'dispatch.json')}>
                Скачать JSON
              </button>
            </div>
          </div>

          <div className="results__grid">
            <article className="results__card">
              <div className="results__title">Итоговый JSON</div>
              <pre className="results__text">
                {JSON.stringify(dispatchResult.combined, null, 2) || '—'}
              </pre>
            </article>

            {Object.values(dispatchResult.services).map((service) => (
              <article key={service.service} className="results__card">
                <div className="results__title">{service.service}</div>
                <p className="results__meta">
                  <strong>URL:</strong> {service.url}
                  <br />
                  <strong>Статус:</strong> {service.status ?? '—'}
                  {service.used_fallback && (
                    <>
                      <br />
                      <strong>Фоллбек:</strong> {service.fallback_status ?? '—'}
                    </>
                  )}
                </p>
                <pre className="results__text">
                  {service.response
                    ? JSON.stringify(service.response, null, 2)
                    : service.error ?? '—'}
                </pre>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}