import { AdminMaterialList } from "@/components/admin/admin-material-list";
import { AdminUploadForm } from "@/components/admin/admin-upload-form";

export default function AdminPage() {
  return (
    <main className="grid gap-6">
      <h1 className="text-3xl">Knowledge & media management</h1>
      <AdminMaterialList />
      <AdminUploadForm />
    </main>
  );
}
