export default function Loading() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="flex flex-col items-center gap-4">
        <div className="w-16 h-16 rounded-xl bg-gradient-to-br from-orange-500 to-red-600 animate-pulse" />
        <p className="text-sm text-neutral-500">Loading...</p>
      </div>
    </div>
  );
}
