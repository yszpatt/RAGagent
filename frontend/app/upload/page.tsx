import { redirect } from "next/navigation";

// 旧入口：上传功能已并入「知识库」页。
export default function UploadRedirect() {
  redirect("/documents");
}
