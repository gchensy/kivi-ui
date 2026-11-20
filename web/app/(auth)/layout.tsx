import { AuthFrame } from "@/components/kivi/auth-frame";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return <AuthFrame>{children}</AuthFrame>;
}
