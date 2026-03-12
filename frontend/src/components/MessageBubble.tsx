import { useState } from "react";
import { ThumbsUp, ThumbsDown, User, Bot, FileText, Image } from "lucide-react";
import { useChatStore } from "../store/chatStore";
import { queryApi } from "../api/client";
import type { Message, Citation } from "../types";

interface Props {
  message: Message;
}

function CitationBadge({ citation, onClick }: { citation: Citation; onClick: () => void }) {
  const icon = citation.content_type === "image_caption"
    ? <Image className="w-3 h-3" />
    : <FileText className="w-3 h-3" />;

  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-700 hover:bg-blue-200 px-2 py-0.5 rounded-full transition-colors ml-1 font-medium"
    >
      {icon}
      [{citation.label}]
    </button>
  );
}

function renderContentWithCitations(
  content: string,
  citations: Citation[],
  onCitationClick: (c: Citation) => void
) {
  if (!citations.length) return <p className="whitespace-pre-wrap text-sm leading-relaxed">{content}</p>;

  // Replace [Chunk-N] references with interactive badges
  const parts: React.ReactNode[] = [];
  const regex = /\[Chunk-(\d+)\]/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(content)) !== null) {
    const idx = parseInt(match[1]) - 1;
    const citation = citations[idx];
    parts.push(content.slice(lastIndex, match.index));
    if (citation) {
      parts.push(
        <CitationBadge
          key={match.index}
          citation={citation}
          onClick={() => onCitationClick(citation)}
        />
      );
    } else {
      parts.push(match[0]);
    }
    lastIndex = regex.lastIndex;
  }
  parts.push(content.slice(lastIndex));

  return <p className="whitespace-pre-wrap text-sm leading-relaxed">{parts}</p>;
}

export default function MessageBubble({ message }: Props) {
  const { setSelectedCitation, setFeedback } = useChatStore();
  const isUser = message.role === "user";
  const [submittedFeedback, setSubmittedFeedback] = useState<1 | -1 | null>(message.feedback ?? null);

  const handleFeedback = async (value: 1 | -1) => {
    if (!message.query_log_id || submittedFeedback !== null) return;
    try {
      await queryApi.submitFeedback(message.query_log_id, value);
      setFeedback(message.id, value);
      setSubmittedFeedback(value);
    } catch { /* ignore */ }
  };

  if (isUser) {
    return (
      <div className="flex justify-end gap-3">
        <div className="max-w-[75%] bg-blue-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 shadow-sm">
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </div>
        <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center flex-shrink-0 mt-1">
          <User className="w-4 h-4 text-blue-600" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center flex-shrink-0 mt-1 shadow-sm">
        <Bot className="w-4 h-4 text-white" />
      </div>

      <div className="max-w-[80%] flex flex-col gap-2">
        <div className="bg-white rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm border border-gray-100">
          {message.isStreaming && !message.content ? (
            <div className="flex gap-1 py-1">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-2 h-2 rounded-full bg-blue-400 animate-bounce"
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              ))}
            </div>
          ) : (
            renderContentWithCitations(
              message.content,
              message.citations || [],
              setSelectedCitation
            )
          )}
        </div>

        {/* Feedback buttons */}
        {!message.isStreaming && message.query_log_id && (
          <div className="flex items-center gap-2 px-1">
            <span className="text-xs text-gray-400">Was this helpful?</span>
            <button
              onClick={() => handleFeedback(1)}
              disabled={submittedFeedback !== null}
              className={`p-1.5 rounded-lg transition-colors ${
                submittedFeedback === 1
                  ? "bg-green-100 text-green-600"
                  : "text-gray-400 hover:text-green-600 hover:bg-green-50 disabled:cursor-default"
              }`}
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => handleFeedback(-1)}
              disabled={submittedFeedback !== null}
              className={`p-1.5 rounded-lg transition-colors ${
                submittedFeedback === -1
                  ? "bg-red-100 text-red-600"
                  : "text-gray-400 hover:text-red-600 hover:bg-red-50 disabled:cursor-default"
              }`}
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
