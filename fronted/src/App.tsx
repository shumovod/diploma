import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChatMarkdown } from "./components/ChatMarkdown";
import { IconPlus, IconRobot, IconSearch, IconUser, Spinner } from "./components/Icons";
import "./App.css";

const STORAGE_KEY = "student_helper_chats_v1";

type SourceItem = {
  title: string;
  url: string;
  favicon_url: string;
};

type ChatResponse = {
  text: string;
  sources: SourceItem[];
  source_type: string;
};

type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: SourceItem[];
  sourceType?: string;
  error?: boolean;
};

type ChatSession = {
  id: string;
  title: string;
  messages: StoredMessage[];
  updatedAt: number;
};

type SidebarMode = "chats" | "search";

type SearchHit = {
  chatId: string;
  chatTitle: string;
  messageId: string;
  role: "user" | "assistant";
  excerpt: string;
};

function uid() {
  return crypto.randomUUID();
}

function needleFromSearch(q: string) {
  return q.trim().toLowerCase();
}

function buildSearchHits(chats: ChatSession[], needle: string): SearchHit[] {
  if (!needle) return [];
  const hits: SearchHit[] = [];
  for (const c of chats) {
    for (const m of c.messages) {
      const low = m.content.toLowerCase();
      if (!low.includes(needle)) continue;
      const idx = low.indexOf(needle);
      const start = Math.max(0, idx - 36);
      const slice = m.content.slice(start, start + 110);
      const excerpt = `${start > 0 ? "…" : ""}${slice}${m.content.length > start + 110 ? "…" : ""}`;
      hits.push({
        chatId: c.id,
        chatTitle: c.title,
        messageId: m.id,
        role: m.role,
        excerpt,
      });
    }
  }
  return hits;
}

function isHtmlPayload(s: string) {
  const t = s.trimStart();
  return t.startsWith("<!DOCTYPE") || t.startsWith("<html") || t.includes("504 Gateway") || t.includes("502 Bad Gateway");
}

function friendlyHttpError(status: number, body: string): string {
  if (status === 504 || status === 502 || body.includes("upstream timed out") || body.includes("Gateway Time-out")) {
    return "Шлюз не дождался ответа от сервера (запрос долгий). Подождите и нажмите «Запросить ответ снова» или упростите вопрос.";
  }
  if (status === 503) {
    return "Сервис временно недоступен. Попробуйте позже.";
  }
  if (isHtmlPayload(body)) {
    return "Ошибка прокси или сервера вместо JSON. Попробуйте обновить страницу и отправить запрос ещё раз.";
  }
  return body.slice(0, 2000) || `Ошибка ${status}`;
}

async function callChatApi(message: string): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  const rawText = await res.text();
  if (!res.ok) {
    throw new Error(friendlyHttpError(res.status, rawText));
  }
  if (isHtmlPayload(rawText)) {
    throw new Error(friendlyHttpError(res.status, rawText));
  }
  let json: ChatResponse;
  try {
    json = JSON.parse(rawText) as ChatResponse;
  } catch {
    throw new Error("Ответ сервера не в формате JSON");
  }
  const text = typeof json.text === "string" ? json.text : String(json.text ?? "");
  const sources = Array.isArray(json.sources) ? json.sources : [];
  const source_type =
    typeof json.source_type === "string" && json.source_type ? json.source_type : "unknown";
  return { text, sources, source_type };
}

function loadInitial(): { chats: ChatSession[]; activeId: string } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const data = JSON.parse(raw) as { chats?: ChatSession[]; activeChatId?: string };
      if (Array.isArray(data.chats) && data.chats.length) {
        const activeId = data.activeChatId && data.chats.some((c) => c.id === data.activeChatId)
          ? data.activeChatId
          : data.chats[0].id;
        return { chats: data.chats, activeId };
      }
    }
  } catch {}
  const id = uid();
  return {
    chats: [{ id, title: "Новый чат", messages: [], updatedAt: Date.now() }],
    activeId: id,
  };
}

export default function App() {
  const initial = useMemo(() => loadInitial(), []);
  const [chats, setChats] = useState<ChatSession[]>(initial.chats);
  const [activeChatId, setActiveChatId] = useState(initial.activeId);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>("chats");
  const [chatSearch, setChatSearch] = useState("");
  const [highlightMessageId, setHighlightMessageId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ chats, activeChatId }),
      );
    } catch {}
  }, [chats, activeChatId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chats, activeChatId, loading]);

  useEffect(() => {
    if (!highlightMessageId) return;
    const el = document.getElementById(`msg-${highlightMessageId}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightMessageId, activeChatId]);

  const activeChat = chats.find((c) => c.id === activeChatId) ?? chats[0];

  const createChat = useCallback(() => {
    const id = uid();
    const session: ChatSession = {
      id,
      title: "Новый чат",
      messages: [],
      updatedAt: Date.now(),
    };
    setChats((prev) => [session, ...prev]);
    setActiveChatId(id);
    setInput("");
    setHighlightMessageId(null);
    setSidebarMode("chats");
  }, []);

  const appendAssistant = useCallback(
    (chatId: string, json: ChatResponse) => {
      const body = json.text.trim() || "Пустой ответ сервера.";
      const assistantMsg: StoredMessage = {
        id: uid(),
        role: "assistant",
        content: body,
        sources: json.sources,
        sourceType: json.source_type,
      };
      setChats((prev) =>
        prev.map((c) =>
          c.id === chatId
            ? {
                ...c,
                messages: [...c.messages, assistantMsg],
                updatedAt: Date.now(),
              }
            : c,
        ),
      );
    },
    [],
  );

  const send = async () => {
    const message = input.trim();
    if (!message || loading || !activeChat) return;

    const userMsg: StoredMessage = { id: uid(), role: "user", content: message };
    const nextTitle =
      activeChat.title === "Новый чат"
        ? message.length > 44
          ? `${message.slice(0, 44)}…`
          : message
        : activeChat.title;

    setChats((prev) =>
      prev.map((c) =>
        c.id === activeChatId
          ? {
              ...c,
              title: nextTitle,
              messages: [...c.messages, userMsg],
              updatedAt: Date.now(),
            }
          : c,
      ),
    );
    setInput("");
    setHighlightMessageId(null);
    setLoading(true);

    try {
      const json = await callChatApi(message);
      appendAssistant(activeChatId, json);
    } catch (e) {
      const errText = e instanceof Error ? e.message : "Ошибка запроса";
      const assistantMsg: StoredMessage = {
        id: uid(),
        role: "assistant",
        content: errText,
        error: true,
      };
      setChats((prev) =>
        prev.map((c) =>
          c.id === activeChatId
            ? {
                ...c,
                messages: [...c.messages, assistantMsg],
                updatedAt: Date.now(),
              }
            : c,
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  const resendLastOrphan = async () => {
    if (loading || !activeChat) return;
    const msgs = activeChat.messages;
    if (msgs.length === 0) return;
    const last = msgs[msgs.length - 1];
    if (last.role !== "user") return;
    const message = last.content.trim();
    if (!message) return;
    setHighlightMessageId(null);
    setLoading(true);
    try {
      const json = await callChatApi(message);
      appendAssistant(activeChatId, json);
    } catch (e) {
      const errText = e instanceof Error ? e.message : "Ошибка запроса";
      const assistantMsg: StoredMessage = {
        id: uid(),
        role: "assistant",
        content: errText,
        error: true,
      };
      setChats((prev) =>
        prev.map((c) =>
          c.id === activeChatId
            ? {
                ...c,
                messages: [...c.messages, assistantMsg],
                updatedAt: Date.now(),
              }
            : c,
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  const sortedChats = useMemo(
    () => [...chats].sort((a, b) => b.updatedAt - a.updatedAt),
    [chats],
  );

  const searchNeedle = useMemo(() => needleFromSearch(chatSearch), [chatSearch]);

  const searchHits = useMemo(
    () => buildSearchHits(chats, searchNeedle),
    [chats, searchNeedle],
  );

  const lastMessage = activeChat.messages[activeChat.messages.length - 1];
  const orphanUserPending =
    !loading && activeChat.messages.length > 0 && lastMessage?.role === "user";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="sidebar-brand__name">Поступление</span>
        </div>
        <button type="button" className="btn-new-chat" onClick={createChat}>
          <IconPlus />
          <span>Новый чат</span>
        </button>
        <div className="sidebar-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={sidebarMode === "chats"}
            className={`sidebar-tab ${sidebarMode === "chats" ? "sidebar-tab--active" : ""}`}
            onClick={() => {
              setSidebarMode("chats");
              setHighlightMessageId(null);
            }}
          >
            Чаты
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={sidebarMode === "search"}
            className={`sidebar-tab ${sidebarMode === "search" ? "sidebar-tab--active" : ""}`}
            onClick={() => setSidebarMode("search")}
          >
            Поиск
          </button>
        </div>

        {sidebarMode === "search" ? (
          <>
            <div className="sidebar-search">
              <IconSearch />
              <input
                type="search"
                className="sidebar-search__input"
                value={chatSearch}
                onChange={(e) => setChatSearch(e.target.value)}
                placeholder="По всем чатам…"
                autoComplete="off"
                spellCheck={false}
              />
            </div>
            <div className="sidebar-section">Совпадения</div>
            <nav className="sidebar-nav">
              {!searchNeedle ? (
                <p className="sidebar-hint">Введите слово или фразу — покажем сообщения из всех чатов.</p>
              ) : searchHits.length === 0 ? (
                <p className="sidebar-empty">Ничего не найдено</p>
              ) : (
                searchHits.map((h) => (
                  <button
                    key={`${h.chatId}-${h.messageId}`}
                    type="button"
                    className="sidebar-hit"
                    onClick={() => {
                      setActiveChatId(h.chatId);
                      setHighlightMessageId(h.messageId);
                      setSidebarMode("chats");
                      setInput("");
                    }}
                  >
                    <span className="sidebar-hit__chat">{h.chatTitle}</span>
                    <span className="sidebar-hit__role">{h.role === "user" ? "Вы" : "Ответ"}</span>
                    <div className="sidebar-hit__excerpt">
                      <ChatMarkdown content={h.excerpt} compact />
                    </div>
                  </button>
                ))
              )}
            </nav>
          </>
        ) : (
          <>
            <div className="sidebar-section">Чаты</div>
            <nav className="sidebar-nav">
              {sortedChats.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  className={`sidebar-item ${c.id === activeChatId ? "sidebar-item--active" : ""}`}
                  onClick={() => {
                    setActiveChatId(c.id);
                    setInput("");
                    setHighlightMessageId(null);
                  }}
                >
                  <span className="sidebar-item__title">{c.title}</span>
                </button>
              ))}
            </nav>
          </>
        )}
      </aside>

      <div className="main">
        <header className="main-header">
          <h1 className="main-title">Помощь при поступлении</h1>
        </header>

        <div className="messages">
          {activeChat.messages.length === 0 && !loading ? (
            <div className="empty-state">
              <p className="empty-state__lead">Готов, когда ты готов.</p>
              <p className="empty-state__hint">
                Спроси про вузы, баллы, дедлайны и программы — ответ соберётся из базы или из актуального
                поиска.
              </p>
            </div>
          ) : null}

          {activeChat.messages.map((m) => {
            const hit = highlightMessageId === m.id;
            const rowClass =
              m.role === "user"
                ? `msg msg--user${hit ? " msg--search-hit" : ""}`
                : `msg msg--assistant${hit ? " msg--search-hit" : ""}`;
            return m.role === "user" ? (
              <div key={m.id} id={`msg-${m.id}`} className={rowClass}>
                <div className="msg__bubble msg__bubble--user">
                  <p className="msg__text">{m.content}</p>
                </div>
                <IconUser />
              </div>
            ) : (
              <div key={m.id} id={`msg-${m.id}`} className={rowClass}>
                <IconRobot />
                <div className="msg__body">
                  {m.error ? (
                    <div className="msg__error">
                      <pre className="msg__error-pre">{m.content}</pre>
                    </div>
                  ) : (
                    <ChatMarkdown content={m.content} />
                  )}
                  {m.sources && m.sources.length > 0 ? (
                    <div className="msg-sources">
                      <div className="msg-sources__title">Ссылки</div>
                      <ul className="msg-sources__list">
                        {m.sources.map((s) => (
                          <li key={s.url}>
                            {s.favicon_url ? (
                              <img src={s.favicon_url} alt="" width={16} height={16} />
                            ) : null}
                            <a href={s.url} target="_blank" rel="noreferrer">
                              {s.title || s.url}
                            </a>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                  {m.sourceType ? (
                    <div className="msg-meta">Источник: {m.sourceType}</div>
                  ) : null}
                </div>
              </div>
            );
          })}

          {orphanUserPending ? (
            <div className="orphan-banner">
              <p className="orphan-banner__text">
                Ответа на последнее сообщение нет — например, страница обновилась до прихода ответа.
              </p>
              <button type="button" className="orphan-banner__btn" onClick={() => void resendLastOrphan()}>
                Запросить ответ снова
              </button>
            </div>
          ) : null}

          {loading ? (
            <div className="msg msg--assistant msg--pending">
              <IconRobot />
              <div className="msg__body msg__body--pending">
                <Spinner />
                <span className="pending-label">Думаю и ищу ответ…</span>
              </div>
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>

        <div className="composer-wrap">
          <div className="composer">
            <textarea
              className="composer__input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Спросите о поступлении…"
              rows={1}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <button
              type="button"
              className="composer__send"
              disabled={loading || !input.trim()}
              onClick={() => void send()}
            >
              Отправить
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
