import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AppFrame } from "@/components/kivi/app-shell";

/** Signed-in area. The cookie check here is a fast path; the API is the authority. */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  if (!(await cookies()).has("kivi_session")) redirect("/login");
  return <AppFrame>{children}</AppFrame>;
}
