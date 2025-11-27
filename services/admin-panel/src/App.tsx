import React, { useMemo, useState } from "react";

type SpecificationItem = {
  name: string;
  qty: number | null;
  unit: string | null;
  price: number | null;
  amount: number | null;
  country: string | null;
};

type SpecificationJson = {
  items: SpecificationItem[];
  total: number | null;
  vat: number | null;
  warning: string | null;
};

type SplitResponse = Record<string, string | SpecificationJson | null>;
type SpecificationResponse = { spec_json: SpecificationJson | null };

type AiLawyerSection = {
  number: number | null;
  title: string;
  content: string;
};

type AiLawyerResponse = {
  docx_text: string | null;
  specification_text: string | null;
  overall_score: number | null;
  inaccuracy: string | null;
  red_flags: string | null;
  html: string;
  debug_message: string | null;
  sections: AiLawyerSection[];
  specification_json: SpecificationJson | null;
};

type Page = "home" | "slicer" | "ai-lawyer";

const DEFAULT_SLICER_BASE_URL = "http://localhost:8090";
const DEFAULT_AI_BASE_URL = "http://localhost:8092";

type Downloadable = Record<string, unknown>;

function downloadJson(data: Downloadable, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function Hero({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="page__header">
      <div>
        <h1>{title}</h1>
        <p className="page__subtitle">{subtitle}</p>
      </div>
    </header>
  );
}

function SpecificationBlock({ spec }: { spec: SpecificationJson }) {
  return (
    <article className="results__card results__card--wide">
      <div className="results__title">spec_json</div>
      <div className="spec">
        <div className="spec__meta">
          <span>Всего позиций: {spec.items.length}</span>
          <span>
            Итоговая сумма: {spec.total ?? "—"}
            {spec.vat ? ` (НДС ${spec.vat}%)` : ""}
          </span>
          {spec.warning && <span className="spec__warning">{spec.warning}</span>}
        </div>
        <div className="spec__table" role="table">
          <div className="spec__header" role="row">
            <span role="columnheader">Название</span>
            <span role="columnheader">Кол-во</span>
            <span role="columnheader">Ед.</span>
            <span role="columnheader">Цена</span>
            <span role="columnheader">Сумма</span>
            <span role="columnheader">Страна</span>
          </div>
          {spec.items.map((item, index) => (
            <div key={`${item.name}-${index}`} className="spec__row" role="row">
              <span role="cell">{item.name}</span>
              <span role="cell">{item.qty ?? "—"}</span>
              <span role="cell">{item.unit ?? "—"}</span>
              <span role="cell">{item.price ?? "—"}</span>
              <span role="cell">{item.amount ?? "—"}</span>
              <span role="cell">{item.country ?? "—"}</span>
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}

function SlicerPage({ baseUrl }: { baseUrl: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SplitResponse | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!file) {
      setError("Пожалуйста, выберите файл договора.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setLoading(true);
      const sectionsResponse = await fetch(`${baseUrl}/api/sections/split`, {
        method: "POST",
        body: formData,
      });

      if (!sectionsResponse.ok) {
        const message = await sectionsResponse.text();
        throw new Error(message || "Не удалось обработать файл");
      }

      const sectionsJson = (await sectionsResponse.json()) as SplitResponse;

      let specJson: SpecificationResponse | null = null;
      try {
        const specResponse = await fetch(`${baseUrl}/api/specification/parse`, {
          method: "POST",
          body: formData,
        });

        if (specResponse.ok) {
          specJson = (await specResponse.json()) as SpecificationResponse;
        }
      } catch (specError) {
        console.warn("Не удалось получить спецификацию:", specError);
      }

      setResult({ ...sectionsJson, ...(specJson ?? {}) });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Неизвестная ошибка";
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
          {loading ? "Обработка…" : "Отправить"}
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
              <button type="button" onClick={() => downloadJson(result, "sections.json")}>
                Скачать JSON
              </button>
            </div>
          </div>

          <div className="results__grid">
            {Object.entries(result)
              .filter(([key]) => key.startsWith("part_"))
              .map(([key, value]) => (
                <article key={key} className="results__card">
                  <div className="results__title">{key}</div>
                  <pre className="results__text">{typeof value === "string" ? value || "—" : "—"}</pre>
                </article>
              ))}

            {"spec_json" in result && result.spec_json && (
              <SpecificationBlock spec={result.spec_json as SpecificationJson} />
            )}
          </div>
        </section>
      )}
    </div>
  );
}

function AiLawyerPage({ baseUrl }: { baseUrl: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AiLawyerResponse | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setResult(null);

    if (!file) {
      setError("Загрузите JSON, полученный из Document Slicer.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setLoading(true);
      const response = await fetch(`${baseUrl}/api/sections/full-prepared`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Не удалось обработать файл");
      }

      const data = (await response.json()) as AiLawyerResponse;
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Неизвестная ошибка";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <Hero
        title="AI Lawyer — проверка адаптированного эндпойнта"
        subtitle="Эндпойнт адаптирован от /sections/full: принимает JSON с part_0–part_16 (результат Document Slicer) и возвращает отчёт."
      />

      <form className="upload" onSubmit={handleSubmit}>
        <label className="upload__field">
          <span>Файл секций (JSON из Document Slicer)</span>
          <input
            type="file"
            accept="application/json,.json"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>

        <p className="upload__hint">
          Сначала загрузите договор на странице <strong>Document Slicer</strong>, скачайте полученный sections.json и отправьте его сюда.
        </p>

        <button className="upload__button" type="submit" disabled={loading}>
          {loading ? "Обработка…" : "Отправить"}
        </button>
      </form>

      {error && <div className="alert alert--error">{error}</div>}

      {result && (
        <section className="results">
          <div className="results__header">
            <h2>Результат AI Lawyer</h2>
            <div className="results__actions">
              <button type="button" onClick={() => setResult(null)}>
                Очистить
              </button>
              <button type="button" onClick={() => downloadJson(result, "ai_lawyer.json")}>
                Скачать JSON
              </button>
            </div>
          </div>

          <div className="results__grid">
            <article className="results__card">
              <div className="results__title">overall_score</div>
              <div className="results__text">{result.overall_score ?? "—"}</div>
            </article>
            <article className="results__card">
              <div className="results__title">inaccuracy</div>
              <div className="results__text">{result.inaccuracy ?? "—"}</div>
            </article>
            <article className="results__card">
              <div className="results__title">red_flags</div>
              <div className="results__text">{result.red_flags ?? "—"}</div>
            </article>
            <article className="results__card">
              <div className="results__title">debug_message</div>
              <div className="results__text">{result.debug_message ?? "—"}</div>
            </article>

            {result.specification_json && <SpecificationBlock spec={result.specification_json} />}

            {result.sections && result.sections.length > 0 && (
              <article className="results__card results__card--wide">
                <div className="results__title">Разделы</div>
                <ul className="results__list">
                  {result.sections.map((section) => (
                    <li key={`${section.title}-${section.number ?? "head"}`}>
                      <strong>{section.number ? `${section.number}. ${section.title}` : section.title}</strong>
                      <p>{section.content || "—"}</p>
                    </li>
                  ))}
                </ul>
              </article>
            )}

            {result.html && (
              <article className="results__card results__card--wide">
                <div className="results__title">HTML отчёт</div>
                <div className="results__html" dangerouslySetInnerHTML={{ __html: result.html }} />
              </article>
            )}

            {result.docx_text && (
              <article className="results__card results__card--wide">
                <div className="results__title">docx_text</div>
                <div className="results__html" dangerouslySetInnerHTML={{ __html: result.docx_text }} />
              </article>
            )}

            {result.specification_text && (
              <article className="results__card results__card--wide">
                <div className="results__title">specification_text</div>
                <pre className="results__text">{result.specification_text}</pre>
              </article>
            )}
          </div>
        </section>
      )}
    </div>
  );
}

export default function App() {
  const slicerBaseUrl = useMemo(() => {
    const envUrl = import.meta.env.VITE_SLICER_API_BASE_URL as string | undefined;
    return envUrl?.trim() || DEFAULT_SLICER_BASE_URL;
  }, []);

  const aiBaseUrl = useMemo(() => {
    const envUrl = import.meta.env.VITE_AI_LAWYER_API_BASE_URL as string | undefined;
    return envUrl?.trim() || DEFAULT_AI_BASE_URL;
  }, []);

  const [activePage, setActivePage] = useState<Page>("home");

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar__title">Документ-сервисы</div>
        <button
          className={`sidebar__link ${activePage === "home" ? "sidebar__link--active" : ""}`}
          onClick={() => setActivePage("home")}
        >
          Главная
        </button>
        <button
        className={`sidebar__link ${activePage === "slicer" ? "sidebar__link--active" : ""}`}
          onClick={() => setActivePage("slicer")}
        >
          Document Slicer
        </button>
        <button
        className={`sidebar__link ${activePage === "ai-lawyer" ? "sidebar__link--active" : ""}`}
          onClick={() => setActivePage("ai-lawyer")}
        >
          AI Lawyer
        </button>
        <div className="sidebar__hint">Фронтенд статичный и не зависит от сервисов до момента запроса.</div>
      </aside>

      <main className="content">
        {activePage === "home" && (
          <div className="page">
            <Hero
              title="Фронтенд проверки сервисов"
              subtitle="Выберите сервис слева: Document Slicer разбивает документ на части, AI Lawyer формирует адаптированный отчёт. Фронтенд запускается отдельно и обращается к API только по клику."
            />
            <div className="home__cards">
              <div className="home__card">
                <h3>Document Slicer</h3>
                <p>Работает с эндпойнтами /api/sections/split и /api/specification/parse.</p>
                <p className="home__note">Базовый URL: {slicerBaseUrl}</p>
                <button onClick={() => setActivePage("slicer")}>Перейти</button>
              </div>
              <div className="home__card">
                <h3>AI Lawyer</h3>
                <p>Принимает JSON с part_0–part_16 от Document Slicer и возвращает отчёт.</p>
                <p className="home__note">Базовый URL: {aiBaseUrl}</p>
                <button onClick={() => setActivePage("ai-lawyer")}>Перейти</button>
              </div>
            </div>
          </div>
        )}

        {activePage === "slicer" && <SlicerPage baseUrl={slicerBaseUrl} />}
        {activePage === "ai-lawyer" && <AiLawyerPage baseUrl={aiBaseUrl} />}
      </main>
    </div>
  );
}