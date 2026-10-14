import { ChatApp } from "@/components/chat/ChatApp";
import { parseAppMode } from "@/lib/appMode";

export default function ChatPage({
  searchParams,
}: {
  searchParams: { mode?: string };
}) {
  return <ChatApp initialModeOverride={parseAppMode(searchParams?.mode)} />;
}
