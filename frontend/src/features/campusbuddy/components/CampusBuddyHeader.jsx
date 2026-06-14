export default function CampusBuddyHeader({ eyebrow, title, children }) {
  return (
    <header className="cb-header">
      <span>{eyebrow}</span>
      <h1>{title}</h1>
      {children ? <p>{children}</p> : null}
    </header>
  );
}
