import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = "https://akudmqkicndamnjjidad.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFrdWRtcWtpY25kYW1uamppZGFkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMyMTUwMjcsImV4cCI6MjA4ODc5MTAyN30.7xX6Rwbd2LN9EMNTTX9B8QSgauZqsfTThVf-8KXCI_0";

export const supabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
