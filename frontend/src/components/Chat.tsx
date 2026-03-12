import { useEffect, useRef, useState } from "react";
import { Send, Trash2, RefreshCw, BookOpen } from "lucide-react";
import { useChatStore, useAuthStore } from "../store/chatStore";
import { streamQuery, queryApi } from "../api/client";
import MessageBubble from "./MessageBubble";
import CitationPanel from "./CitationPanel";
import type { Citation } from "../types";

export default function Chat() {
  const [input, setInput] = useState("");
  const [namespace, setNamespace] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  const { sessionId } = useAuthStore();
  const {
    messages, isStreaming, statusMessage,
    addUserMessage, startAssistantMessage, appendToken,
    finishMessage, setStatus, setStreaming, clearMessages,
    setActiveCitations, activeCitations, selectedCitation, setSelectedCitation,
  } = useChatStore();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, statusMessage]);

  const handleSubmit = () => {
    if (!input.trim() || isStreaming) return;
    const question = input.trim();
    setInput("");

    addUserMessage(question);
    const assistantId = startAssistantMessage();
    let pendingCitations: Citation[] = [];

    cancelRef.current = streamQuery(question, sessionId, namespace || undefined, {
      onStatus: setStatus,
      onCitations: (citations) => {
        pendingCitations = citations;
        setActiveCitations(citations);
      },
      onToken: (token) => appendToken(assistantId, token),
      onDone: (data) => {
        finishMessage(assistantId, pendingCitations, data.query_log_id);
        cancelRef.current = null;
      },
      onError: (msg) => {
        appendToken(assistantId, `\n\n⚠️ Error: ${msg}`);
        finishMessage(assistantId, [], "");
      },
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleClear = async () => {
    if (cancelRef.current) cancelRef.current();
    clearMessages();
    await queryApi.clearHistory(sessionId);
  };

  return (
    <div className="flex h-full">
      {/* Main chat area */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Header */}
        <div className="border-b border-gray-200 px-6 py-4 flex items-center justify-between bg-white shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shadow">
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-gray-900">EDU-RAG Tutor</h1>
              <p className="text-xs text-gray-500">Ask anything from your textbooks</p>
            </div>
          </div>
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-red-600 transition-colors px-3 py-1.5 rounded-lg hover:bg-red-50"
          >
            <Trash2 className="w-4 h-4" />
            Clear
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4 bg-gray-50">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center py-20">
              <div className="w-16 h-16 rounded-2xl bg-blue-100 flex items-center justify-center mb-4">
                <BookOpen className="w-8 h-8 text-blue-600" />
              </div>
              <h2 className="text-xl font-semibold text-gray-700 mb-2">Ask your textbook anything</h2>
              <p className="text-gray-500 max-w-sm text-sm">
                All answers are grounded in your course materials with citations. Start by typing a question below.
              </p>
              <div className="mt-6 grid grid-cols-1 gap-2 w-full max-w-sm">
                {[
                  "What is Newton's second law?",
                  "Explain photosynthesis step by step",
                  "What are the causes of World War I?",
                ].map((q) => (
                  <button
                    key={q}
                    onClick={() => { setInput(q); }}
                    className="text-left text-sm text-blue-700 bg-blue-50 hover:bg-blue-100 px-4 py-2.5 rounded-xl transition-colors border border-blue-100"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}

          {statusMessage && (
            <div className="flex items-center gap-2 text-sm text-blue-600 px-4 py-2 bg-blue-50 rounded-xl w-fit">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              {statusMessage}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="border-t border-gray-200 bg-white px-4 py-4">
          {/* Optional namespace filter */}
          <div className="mb-2">
            <input
              type="text"
              value={namespace}
              onChange={(e) => setNamespace(e.target.value)}
              placeholder="Filter by textbook namespace (optional)"
              className="w-full text-xs text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-blue-400"
            />
          </div>
          <div className="flex gap-3 items-end">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question from your textbook..."
              rows={2}
              disabled={isStreaming}
              className="flex-1 resize-none border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50 disabled:bg-gray-50"
            />
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || isStreaming}
              className="w-12 h-12 flex items-center justify-center rounded-xl bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-sm flex-shrink-0"
            >
              {isStreaming
                ? <RefreshCw className="w-4 h-4 animate-spin" />
                : <Send className="w-4 h-4" />
              }
            </button>
          </div>
        </div>
      </div>

      {/* Citation panel */}
      {activeCitations.length > 0 && (
        <CitationPanel
          citations={activeCitations}
          selectedCitation={selectedCitation}
          onSelect={setSelectedCitation}
        />
      )}
    </div>
  );
}
