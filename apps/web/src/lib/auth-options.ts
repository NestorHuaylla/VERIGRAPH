import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import KeycloakProvider from "next-auth/providers/keycloak";

import type { AuthResponse, UserRole } from "@/lib/verigraph-types";

const defaultApiPort = process.env.NEXT_PUBLIC_API_PORT?.trim() || "8000";
const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.trim() || `http://localhost:${defaultApiPort}`;
const keycloakIssuer = process.env.KEYCLOAK_ISSUER?.trim();
const keycloakClientId = process.env.KEYCLOAK_CLIENT_ID?.trim();
const keycloakClientSecret = process.env.KEYCLOAK_CLIENT_SECRET?.trim();

const rolePriority: UserRole[] = ["admin", "legal", "analyst", "reporter"];

export const authOptions: NextAuthOptions = {
  session: {
    strategy: "jwt"
  },
  providers: [
    CredentialsProvider({
      name: "VERIGRAPH",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" }
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials.password) {
          return null;
        }

        const response = await fetch(`${apiBaseUrl}/api/v1/auth/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json"
          },
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password
          })
        });

        if (!response.ok) {
          return null;
        }

        const auth = (await response.json()) as AuthResponse;
        return {
          id: auth.user.id,
          email: auth.user.email,
          role: auth.user.role,
          is_active: auth.user.is_active,
          accessToken: auth.access_token
        };
      }
    }),
    ...(keycloakIssuer && keycloakClientId && keycloakClientSecret
      ? [
          KeycloakProvider({
            issuer: keycloakIssuer,
            clientId: keycloakClientId,
            clientSecret: keycloakClientSecret
          })
        ]
      : [])
  ],
  callbacks: {
    async jwt({ token, user, account, profile }) {
      if (user) {
        const maybeUser = user as typeof user & {
          role?: UserRole;
          is_active?: boolean;
          accessToken?: string;
        };
        token.user = {
          id: String(maybeUser.id),
          email: String(maybeUser.email || token.email || ""),
          role: maybeUser.role || "reporter",
          is_active: maybeUser.is_active ?? true
        };
        if (maybeUser.accessToken) {
          token.accessToken = maybeUser.accessToken;
        }
      }

      if (account?.provider === "keycloak") {
        token.accessToken = account.access_token;
        token.user = {
          id: String(token.sub || ""),
          email: String(token.email || ""),
          role: extractKeycloakRole(profile),
          is_active: true
        };
      }

      return token;
    },
    async session({ session, token }) {
      session.accessToken = typeof token.accessToken === "string" ? token.accessToken : undefined;
      if (token.user) {
        session.user = token.user;
      }
      return session;
    }
  },
  pages: {
    signIn: "/login"
  }
};

function extractKeycloakRole(profile: unknown): UserRole {
  const roles = new Set<string>();
  if (typeof profile === "object" && profile !== null) {
    const profileRecord = profile as Record<string, unknown>;
    collectRoles(profileRecord.roles, roles);
    const realmAccess = profileRecord.realm_access;
    if (typeof realmAccess === "object" && realmAccess !== null) {
      collectRoles((realmAccess as Record<string, unknown>).roles, roles);
    }
    const resourceAccess = profileRecord.resource_access;
    if (typeof resourceAccess === "object" && resourceAccess !== null && keycloakClientId) {
      const clientAccess = (resourceAccess as Record<string, unknown>)[keycloakClientId];
      if (typeof clientAccess === "object" && clientAccess !== null) {
        collectRoles((clientAccess as Record<string, unknown>).roles, roles);
      }
    }
  }

  for (const role of rolePriority) {
    if (roles.has(role) || roles.has(`verigraph_${role}`)) {
      return role;
    }
  }
  return "reporter";
}

function collectRoles(value: unknown, roles: Set<string>): void {
  if (!Array.isArray(value)) {
    return;
  }
  for (const role of value) {
    roles.add(String(role).trim().toLowerCase());
  }
}
