import { useEffect, useState, useRef } from "react";
import { Upload, RefreshCw, CheckCircle, AlertCircle, Clock, BarChart2, Users, FileText, Zap } from "lucide-react";
import { adminApi } from "../api/client";
import type { Document, Analytics, Course } from "../types";

export default function AdminDashboard() {
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [users, setUsers] = useState<Array<{ id: string; email: string; full_name: string; role: string }>>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState("");
  const [tab, setTab] = useState<"overview" | "documents" | "courses">("overview");
  const fileRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [courseId, setCourseId] = useState("");
  const [courseName, setCourseName] = useState("");
  const [courseDescription, setCourseDescription] = useState("");
  const [creatingCourse, setCreatingCourse] = useState(false);
  const [courseMsg, setCourseMsg] = useState("");
  const [selectedEnrollCourseId, setSelectedEnrollCourseId] = useState("");
  const [selectedUserId, setSelectedUserId] = useState("");
  const [enrolling, setEnrolling] = useState(false);
  const [enrollMsg, setEnrollMsg] = useState("");

  const refresh = async () => {
    const [a, d, c, u] = await Promise.all([
      adminApi.getAnalytics(),
      adminApi.listDocuments(),
      adminApi.listCourses(),
      adminApi.listUsers(),
    ]);
    setAnalytics(a);
    setDocuments(d);
    setCourses(c);
    setUsers(u);
  };

  useEffect(() => { refresh(); }, []);

  const handleCreateCourse = async () => {
    if (!courseName.trim()) return;
    setCreatingCourse(true);
    setCourseMsg("");
    try {
      await adminApi.createCourse(courseName.trim(), courseDescription.trim() || undefined);
      setCourseMsg("✅ Course created");
      setCourseName("");
      setCourseDescription("");
      await refresh();
    } catch (e: any) {
      setCourseMsg(`❌ ${e.message || "Failed to create course"}`);
    } finally {
      setCreatingCourse(false);
    }
  };

  const handleEnroll = async () => {
    if (!selectedEnrollCourseId || !selectedUserId) return;
    setEnrolling(true);
    setEnrollMsg("");
    try {
      await adminApi.enrollUser(selectedEnrollCourseId, selectedUserId);
      const selectedCourse = courses.find((c) => c.id === selectedEnrollCourseId);
      const selectedUser = users.find((u) => u.id === selectedUserId);
      setEnrollMsg(`✅ Enrolled ${selectedUser?.full_name || "user"} to ${selectedCourse?.name || "course"}`);
    } catch (e: any) {
      setEnrollMsg(`❌ ${e.message || "Failed to enroll user"}`);
    } finally {
      setEnrolling(false);
    }
  };

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !title) return;
    setUploading(true);
    setUploadMsg("");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title);
    if (courseId) fd.append("course_id", courseId);
    try {
      const r = await adminApi.ingestDocument(fd);
      setUploadMsg(`✅ Queued: ${r.document_id}. Namespace: ${r.namespace}`);
      setTitle("");
      if (fileRef.current) fileRef.current.value = "";
      setTimeout(refresh, 2000);
    } catch (e: any) {
      setUploadMsg(`❌ ${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  const statusIcon = (status: string) => {
    switch (status) {
      case "completed": return <CheckCircle className="w-4 h-4 text-green-500" />;
      case "processing": return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />;
      case "failed": return <AlertCircle className="w-4 h-4 text-red-500" />;
      default: return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="max-w-5xl mx-auto p-8">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Admin Dashboard</h1>
          <button onClick={refresh} className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700">
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 bg-white rounded-xl p-1 border border-gray-200 w-fit">
          {(["overview", "documents", "courses"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors capitalize ${
                tab === t ? "bg-blue-600 text-white shadow" : "text-gray-600 hover:text-gray-900"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Overview tab */}
        {tab === "overview" && analytics && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {[
              { label: "Total Queries", value: analytics.total_queries, icon: BarChart2, color: "blue" },
              { label: "Active Users", value: analytics.total_users, icon: Users, color: "indigo" },
              { label: "Documents", value: analytics.total_documents, icon: FileText, color: "teal" },
              { label: "Avg Latency", value: `${analytics.avg_latency_ms}ms`, icon: Zap, color: "orange" },
              { label: "👍 Helpful", value: analytics.positive_feedback, icon: null, color: "green" },
              { label: "👎 Unhelpful", value: analytics.negative_feedback, icon: null, color: "red" },
            ].map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="bg-white rounded-2xl border border-gray-100 p-5">
                <div className="text-2xl font-bold text-gray-900 mb-1">{value}</div>
                <div className="text-sm text-gray-500">{label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Documents tab */}
        {tab === "documents" && (
          <div className="space-y-4">
            {/* Upload form */}
            <div className="bg-white rounded-2xl border border-gray-100 p-6">
              <h3 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
                <Upload className="w-4 h-4 text-blue-600" /> Upload Textbook
              </h3>
              <div className="grid grid-cols-1 gap-3">
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Textbook title (e.g. Physics Grade 10 NCERT)"
                  className="border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <select
                  value={courseId}
                  onChange={(e) => setCourseId(e.target.value)}
                  className="border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">No course (public)</option>
                  {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <input ref={fileRef} type="file" accept=".pdf" className="text-sm text-gray-500" />
                <button
                  onClick={handleUpload}
                  disabled={uploading || !title}
                  className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2.5 rounded-xl text-sm font-medium transition-colors"
                >
                  {uploading ? <><RefreshCw className="w-4 h-4 animate-spin" /> Processing...</> : "Upload & Ingest"}
                </button>
                {uploadMsg && <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded-xl">{uploadMsg}</p>}
              </div>
            </div>

            {/* Documents list */}
            <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    {["Title", "Namespace", "Pages", "Chunks", "Status"].map((h) => (
                      <th key={h} className="text-left text-xs font-semibold text-gray-500 px-4 py-3">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                      <td className="px-4 py-3 text-sm font-medium text-gray-900">{doc.title}</td>
                      <td className="px-4 py-3 text-xs text-gray-500 font-mono">{doc.namespace}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{doc.total_pages ?? "—"}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{doc.total_chunks ?? "—"}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          {statusIcon(doc.status)}
                          <span className="text-xs capitalize text-gray-600">{doc.status}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {documents.length === 0 && (
                <div className="text-center text-gray-400 py-8 text-sm">No documents yet</div>
              )}
            </div>
          </div>
        )}

        {/* Courses tab */}
        {tab === "courses" && (
          <div className="space-y-4">
            <div className="bg-white rounded-2xl border border-gray-100 p-6">
              <h3 className="font-semibold text-gray-800 mb-4">Create Course</h3>
              <div className="grid grid-cols-1 gap-3">
                <input
                  type="text"
                  value={courseName}
                  onChange={(e) => setCourseName(e.target.value)}
                  placeholder="Course name (e.g. Biology Class 9)"
                  className="border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <textarea
                  value={courseDescription}
                  onChange={(e) => setCourseDescription(e.target.value)}
                  placeholder="Course description (optional)"
                  rows={3}
                  className="border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                />
                <button
                  onClick={handleCreateCourse}
                  disabled={creatingCourse || !courseName.trim()}
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2.5 rounded-xl text-sm font-medium transition-colors"
                >
                  {creatingCourse ? "Creating..." : "Create Course"}
                </button>
                {courseMsg && <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded-xl">{courseMsg}</p>}
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-100 p-6">
              <h3 className="font-semibold text-gray-800 mb-4">Enroll User To Course</h3>
              <div className="grid grid-cols-1 gap-3">
                <select
                  value={selectedEnrollCourseId}
                  onChange={(e) => setSelectedEnrollCourseId(e.target.value)}
                  className="border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Select course</option>
                  {courses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <select
                  value={selectedUserId}
                  onChange={(e) => setSelectedUserId(e.target.value)}
                  className="border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Select user</option>
                  {users
                    .filter((u) => u.role !== "admin")
                    .map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.full_name} ({u.role}) - {u.email}
                      </option>
                    ))}
                </select>
                <button
                  onClick={handleEnroll}
                  disabled={enrolling || !selectedEnrollCourseId || !selectedUserId}
                  className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white py-2.5 rounded-xl text-sm font-medium transition-colors"
                >
                  {enrolling ? "Enrolling..." : "Enroll User"}
                </button>
                {enrollMsg && <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded-xl">{enrollMsg}</p>}
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-100 p-6">
              <h3 className="font-semibold text-gray-800 mb-4">Courses ({courses.length})</h3>
              {courses.length === 0 ? (
                <p className="text-sm text-gray-400">No courses created yet.</p>
              ) : (
                <div className="space-y-2">
                  {courses.map((c) => (
                    <div key={c.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
                      <div>
                        <div className="font-medium text-gray-800 text-sm">{c.name}</div>
                        {c.description && <div className="text-xs text-gray-500">{c.description}</div>}
                      </div>
                      <span className="text-xs text-gray-400 font-mono">{c.id.slice(0, 8)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
