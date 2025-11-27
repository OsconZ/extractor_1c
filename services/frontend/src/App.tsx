import { useMemo, useState } from 'react';

type SplitResponse = Record<string, string>;

const DEFAULT_BASE_URL = 'http://localhost:8090';

function downloadJson(data: SplitResponse) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'sections.json';
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const baseUrl = useMemo(() => {
    const envUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
    return envUrl?.trim() || DEFAULT_BASE_URL;
  }, []);

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
      const response = await fetch(`${baseUrl}/api/sections/split`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || 'Не удалось обработать файл');
      }

      const json = (await response.json()) as SplitResponse;
      setResult(json);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Неизвестная ошибка';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <h1>Проверка сервиса нарезки документов</h1>
          <p className="page__subtitle">
            Подгрузите файл договора, чтобы получить секции part_0 – part_16. В поле ниже можно сохранить
            результат в JSON.
          </p>
        </div>
        <span className="page__badge">UI для /api/sections/split</span>
      </header>

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
              <button type="button" onClick={() => downloadJson(result)}>
                Скачать JSON
              </button>
            </div>
          </div>

          <div className="results__grid">
            {Object.entries(result).map(([key, value]) => (
              <article key={key} className="results__card">
                <div className="results__title">{key}</div>
                <pre className="results__text">{value || '—'}</pre>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}