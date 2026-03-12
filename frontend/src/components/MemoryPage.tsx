import { useEffect, useState } from "react";
import { Brain, Trash2, TrendingUp, TrendingDown, BookOpen } from "lucide-react";
import { memoryApi } from "../api/client";
import type { MemoryProfile } from "../types";

export default function MemoryPage() {
  const [profile, setProfile] = useState<MemoryProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    memoryApi.getProfile().then(setProfile).finally(() => setLoading(false));
  }, []);

  const handleDelete = async () => {
    if (!confirm("Delete all your learning memory? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await memoryApi.deleteProfile();
      setProfile(null);
    } finally {
      setDeleting(false);
    }
  };

  if (loading) return (
    <div className="flex items-center justify-center h-full text-gray-400">Loading profile...</div>
  );

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-xl bg-purple-100 flex items-center justify-center">
          <Brain className="w-5 h-5 text-purple-600" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Learning Profile</h1>
          <p className="text-sm text-gray-500">Your personalised memory used to tailor answers</p>
        </div>
      </div>

      {!profile || profile.total_queries === 0 ? (
        <div className="bg-gray-50 rounded-2xl p-8 text-center text-gray-500">
          <Brain className="w-10 h-10 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No profile data yet</p>
          <p className="text-sm mt-1">Ask some questions to build your learning profile.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Stats row */}
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white rounded-2xl border border-gray-100 p-5">
              <div className="text-3xl font-bold text-blue-600">{profile.total_queries}</div>
              <div className="text-sm text-gray-500 mt-1">Total questions asked</div>
            </div>
            <div className="bg-white rounded-2xl border border-gray-100 p-5">
              <div className="text-2xl font-bold text-indigo-600 capitalize">{profile.learning_level}</div>
              <div className="text-sm text-gray-500 mt-1">Learning level</div>
            </div>
          </div>

          {/* Topics */}
          {profile.frequently_asked_topics.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-100 p-5">
              <div className="flex items-center gap-2 mb-3">
                <BookOpen className="w-4 h-4 text-blue-500" />
                <h3 className="font-medium text-gray-800">Recently Studied Topics</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {profile.frequently_asked_topics.map((t) => (
                  <span key={t} className="text-xs bg-blue-50 text-blue-700 px-3 py-1 rounded-full border border-blue-100">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Strong areas */}
          {profile.strong_areas.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-100 p-5">
              <div className="flex items-center gap-2 mb-3">
                <TrendingUp className="w-4 h-4 text-green-500" />
                <h3 className="font-medium text-gray-800">Strong Areas</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {profile.strong_areas.map((t) => (
                  <span key={t} className="text-xs bg-green-50 text-green-700 px-3 py-1 rounded-full border border-green-100">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Weak areas */}
          {profile.weak_areas.length > 0 && (
            <div className="bg-white rounded-2xl border border-gray-100 p-5">
              <div className="flex items-center gap-2 mb-3">
                <TrendingDown className="w-4 h-4 text-orange-500" />
                <h3 className="font-medium text-gray-800">Areas for Improvement</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                {profile.weak_areas.map((t) => (
                  <span key={t} className="text-xs bg-orange-50 text-orange-700 px-3 py-1 rounded-full border border-orange-100">
                    {t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* GDPR delete */}
          <div className="bg-red-50 rounded-2xl border border-red-100 p-5">
            <h3 className="font-medium text-red-800 mb-1">Delete My Memory</h3>
            <p className="text-sm text-red-600 mb-3">
              Permanently delete all personalisation data associated with your account.
            </p>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="flex items-center gap-2 text-sm bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-xl transition-colors disabled:opacity-50"
            >
              <Trash2 className="w-4 h-4" />
              {deleting ? "Deleting..." : "Delete all memory"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
