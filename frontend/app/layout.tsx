import type { Metadata } from "next";
import FloatingAIAssistant from "@/components/chat/FloatingAIAssistant";
import { AssistantErrorBoundary } from "@/components/chat/AssistantErrorBoundary";
import "./globals.css";

export const metadata: Metadata = {
  title: "小易电商助手",
  description: "基于真实电商数据的 AI Agent 客服演示平台。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body suppressHydrationWarning>
        {children}
        <AssistantErrorBoundary>
          <FloatingAIAssistant />
        </AssistantErrorBoundary>
      </body>
    </html>
  );
}
