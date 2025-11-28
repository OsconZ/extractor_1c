import React, { useState } from 'react';
import { Hero } from '../components/Hero';
import { SpecificationBlock } from '../components/SpecificationBlock';
import { SpecificationJson, SplitResponse, SpecificationResponse } from '../types/api';
import { downloadJson } from '../utils/download';

interface SlicerPageProps {
  baseUrl: string;
}

export function SlicerPage({ baseUrl }: SlicerPageProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SplitResponse | null>(null);

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
    </div>
  );
}