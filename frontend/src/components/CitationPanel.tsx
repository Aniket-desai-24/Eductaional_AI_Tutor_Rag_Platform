import { X, FileText, Image, Table, Sigma, BookOpen, Hash } from "lucide-react";
import type { Citation } from "../types";

interface Props {
  citations: Citation[];
  selectedCitation: Citation | null;
  onSelect: (c: Citation | null) => void;
}

const contentTypeIcon = (type: string) => {
  switch (type) {
    case "image_caption": return <Image className="w-4 h-4 text-purple-500" />;
    case "table": return <Table className="w-4 h-4 text-teal-500" />;
    case "equation": return <Sigma className="w-4 h-4 text-orange-500" />;
    default: return <FileText className="w-4 h-4 text-blue-500" />;
  }
};

const contentTypeLabel = (type: string) => {
  switch (type) {
    case "image_caption": return "Image";
    case "table": return "Table";
    case "equation": return "Equation";
    default: return "Text";
  }
};

export default function CitationPanel({ citations, selectedCitation, onSelect }: Props) {
  return (
    <div className="w-80 border-l border-gray-200 bg-white flex flex-col h-full">
      <div className="px-4 py-4 border-b border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-blue-600" />
          <h3 className="font-semibold text-gray-800 text-sm">Sources ({citations.length})</h3>
        </div>
        {selectedCitation && (
          <button
            onClick={() => onSelect(null)}
            className="p-1 rounded hover:bg-gray-100 text-gray-400"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {selectedCitation ? (
        /* Expanded view */
        <div className="flex-1 overflow-y-auto p-4">
          <div className="mb-3 flex items-center gap-2">
            {contentTypeIcon(selectedCitation.content_type)}
            <span className="text-xs font-medium text-gray-600 uppercase tracking-wide">
              {contentTypeLabel(selectedCitation.content_type)}
            </span>
            <span className="ml-auto text-xs text-blue-600 font-semibold">{selectedCitation.label}</span>
          </div>

          {/* Source metadata */}
          <div className="bg-gray-50 rounded-xl p-3 mb-3 space-y-1.5">
            {selectedCitation.chapter && (
              <div className="flex items-center gap-2 text-xs text-gray-600">
                <Hash className="w-3 h-3" /> Chapter {selectedCitation.chapter}
              </div>
            )}
            {selectedCitation.section && (
              <div className="text-xs text-gray-600 font-medium">{selectedCitation.section}</div>
            )}
            {selectedCitation.page_start && (
              <div className="text-xs text-gray-500">
                Page {selectedCitation.page_start}
                {selectedCitation.page_end && selectedCitation.page_end !== selectedCitation.page_start
                  ? `–${selectedCitation.page_end}` : ""}
              </div>
            )}
            <div className="text-xs text-gray-400">
              Relevance: {Math.round(selectedCitation.score * 100)}%
            </div>
          </div>

          {/* Image preview */}
          {selectedCitation.image_url && (
            <div className="mb-3">
              <img
                src={selectedCitation.image_url}
                alt="Source image"
                className="w-full rounded-xl border border-gray-200"
                loading="lazy"
              />
            </div>
          )}

          {/* Content snippet */}
          <div className="text-sm text-gray-700 leading-relaxed bg-blue-50 rounded-xl p-3 border border-blue-100">
            <p className="text-xs text-blue-600 font-medium mb-1.5">Passage excerpt:</p>
            {selectedCitation.snippet}
            {selectedCitation.snippet.length >= 200 && "…"}
          </div>

          <button
            onClick={() => onSelect(null)}
            className="mt-3 text-xs text-gray-500 hover:text-gray-700 underline"
          >
            ← Back to all sources
          </button>
        </div>
      ) : (
        /* List view */
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {citations.map((citation) => (
            <button
              key={citation.chunk_id}
              onClick={() => onSelect(citation)}
              className="w-full text-left p-3 rounded-xl border border-gray-100 hover:border-blue-200 hover:bg-blue-50 transition-all group"
            >
              <div className="flex items-start gap-2">
                <div className="mt-0.5 flex-shrink-0">{contentTypeIcon(citation.content_type)}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-blue-700">{citation.label}</span>
                    <span className="text-xs text-gray-400">{Math.round(citation.score * 100)}%</span>
                  </div>
                  {(citation.chapter || citation.section) && (
                    <p className="text-xs text-gray-500 truncate mb-1">
                      {citation.chapter && `Ch. ${citation.chapter}`}
                      {citation.chapter && citation.section && " · "}
                      {citation.section}
                    </p>
                  )}
                  <p className="text-xs text-gray-600 line-clamp-2 leading-relaxed">
                    {citation.snippet}
                  </p>
                  {citation.page_start && (
                    <p className="text-xs text-gray-400 mt-1">p. {citation.page_start}</p>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
