import { MessageSquare, Brain, LayoutDashboard, LogOut, BookOpen, Plus } from "lucide-react";
import { useAuthStore, useChatStore } from "../store/chatStore";
import type { User } from "../types";

interface Props {
  activeTab: "chat" | "memory" | "admin";
  onTabChange: (tab: "chat" | "memory" | "admin") => void;
}

export default function Sidebar({ activeTab, onTabChange }: Props) {
  const { user, logout, newSession } = useAuthStore();
  const { clearMessages } = useChatStore();

  const handleNewChat = () => {
    clearMessages();
    newSession();
    onTabChange("chat");
  };

  const handleLogout = () => {
    clearMessages();
    logout();
    onTabChange("chat");
  };

  const navItems = [
    { id: "chat" as const, label: "Chat", icon: MessageSquare },
    { id: "memory" as const, label: "My Profile", icon: Brain },
    ...(user?.role === "admin" ? [{ id: "admin" as const, label: "Admin", icon: LayoutDashboard }] : []),
  ];

  return (
    <div className="w-64 bg-gray-900 text-white flex flex-col h-full">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-gray-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow">
            <BookOpen className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="font-bold text-white text-sm">EDU-RAG</div>
            <div className="text-xs text-gray-400">AI Tutor Platform</div>
          </div>
        </div>
      </div>

      {/* New chat button */}
      <div className="px-4 pt-4">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center gap-2 text-sm bg-blue-600 hover:bg-blue-700 text-white px-4 py-2.5 rounded-xl transition-colors font-medium"
        >
          <Plus className="w-4 h-4" />
          New Conversation
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-4 space-y-1">
        {navItems.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onTabChange(id)}
            className={`w-full flex items-center gap-3 text-sm px-3 py-2.5 rounded-xl transition-colors ${
              activeTab === id
                ? "bg-gray-700 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-800"
            }`}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </button>
        ))}
      </nav>

      {/* User info & logout */}
      <div className="border-t border-gray-800 px-4 py-4">
        {user && (
          <div className="mb-3 px-1">
            <div className="text-sm font-medium text-white truncate">{user.full_name}</div>
            <div className="text-xs text-gray-400 truncate">{user.email}</div>
            <span className="inline-block mt-1 text-xs bg-blue-600/30 text-blue-300 px-2 py-0.5 rounded-full capitalize">
              {user.role}
            </span>
          </div>
        )}
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-2 text-sm text-gray-400 hover:text-red-400 hover:bg-gray-800 px-3 py-2 rounded-xl transition-colors"
        >
          <LogOut className="w-4 h-4" />
          Sign out
        </button>
      </div>
    </div>
  );
}
