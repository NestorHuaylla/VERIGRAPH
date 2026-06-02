import type { UserRole } from "@/lib/verigraph-types";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    user: {
      id: string;
      email: string;
      role: UserRole;
      is_active: boolean;
    };
  }

  interface User {
    role?: UserRole;
    is_active?: boolean;
    accessToken?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    user?: {
      id: string;
      email: string;
      role: UserRole;
      is_active: boolean;
    };
  }
}
