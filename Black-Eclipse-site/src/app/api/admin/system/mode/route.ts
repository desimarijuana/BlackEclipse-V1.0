import { POST as handlePost } from "@/app/admin/system/mode/route";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  return handlePost(request);
}
