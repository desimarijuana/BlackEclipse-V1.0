import { GET as handleGet, POST as handlePost } from "@/app/admin/system/config/route";

export const dynamic = "force-dynamic";

export async function GET() {
  return handleGet();
}

export async function POST(request: Request) {
  return handlePost(request);
}
