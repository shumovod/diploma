export function IconUser() {
  return (
    <svg className="msg-avatar msg-avatar--user" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4Zm0 2c-3.33 0-6 1.67-6 3.75V20h12v-2.25C18 15.67 15.33 14 12 14Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function IconRobot() {
  return (
    <svg className="msg-avatar msg-avatar--bot" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M9 3v2H7a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2V3H9Zm1 2h4v1h-4V5ZM8 9h8v7H8V9Zm2 2v1h4v-1h-4Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function IconSearch() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Zm0-2a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11Z"
        fill="currentColor"
      />
      <path
        d="m16.5 16.5 4.5 4.5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function IconPlus() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function Spinner() {
  return <span className="spinner" role="status" aria-label="Ожидание ответа" />;
}
