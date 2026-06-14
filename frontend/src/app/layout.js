import "./globals.css";
import "../features/campusbuddy/campusBuddy.css";

export const metadata = {
  title: "CampusFlow",
  description: "AI-powered student life OS for attendance, exams, assignments, and campus updates.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
