import type { Metadata } from "next";
import { Geist } from "next/font/google";
import "./globals.css";
import { dictionaries, getLanguage } from "./i18n";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

// Blocking on purpose: the language comes from Accept-Language, so the first HTML must wait for it.
export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const { title, description } = dictionaries[await getLanguage()];
  return { title, description };
}

export default async function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang={await getLanguage()} className={`${geistSans.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
