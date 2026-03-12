import { useState } from "react";
import { useAuthStore } from "./store/chatStore";
import AuthPage from "./components/AuthPage";
import Chat from "./components/Chat";
import Sidebar from "./components/Sidebar";
import MemoryPage from "./components/MemoryPage";
import AdminDashboard from "./components/AdminDashboard";

type Tab = "chat" | "memory" | "admin";

export default function App() {
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<Tab>("chat");

  if (!user) return <AuthPage />;

  return (
    <div className="flex h-screen bg-gray-100 overflow-hidden">
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex-1 min-w-0 overflow-hidden">
        {activeTab === "chat" && <Chat />}
        {activeTab === "memory" && <MemoryPage />}
        {activeTab === "admin" && user.role === "admin" && <AdminDashboard />}
      </main>
    </div>
  );
}
