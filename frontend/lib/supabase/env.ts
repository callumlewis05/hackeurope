const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabasePublishableKey =
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

function missingEnvVarError(name: string) {
  return new Error(`Missing Supabase environment variable: ${name}`);
}

export function getSupabaseUrl() {
  if (!supabaseUrl) {
    throw missingEnvVarError("NEXT_PUBLIC_SUPABASE_URL");
  }

  return supabaseUrl;
}

export function getSupabasePublishableKey() {
  if (!supabasePublishableKey) {
    throw missingEnvVarError(
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY (or NEXT_PUBLIC_SUPABASE_ANON_KEY)",
    );
  }

  return supabasePublishableKey;
}
