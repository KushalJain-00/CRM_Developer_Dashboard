window.CRM_API_BASE = 'https://crm-developer-dashboard.onrender.com';
window.CRM_API_KEY  = '06f618cab6632be0071ef34007f981e3';

// ── Supabase credentials ──────────────────────────────────────────────
// BUG FIX: These were empty, which caused Supabase client to never be
// created and login always failed with "Supabase is not configured".
// Replace the values below with your actual Supabase project credentials.
// Get them from: https://app.supabase.com → Project Settings → API
window.CRM_SUPABASE_URL      = 'https://omqlplhfkriwjubjafgr.supabase.co';
window.CRM_SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9tcWxwbGhma3Jpd2p1YmphZmdyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY0MDc2MjcsImV4cCI6MjA5MTk4MzYyN30.PdYblAyMC9HWg7Q6uYwro9Tx7nscpthOGCac7F2EXpM';
// ── EML Email Extractor — Separate Supabase Project ──────────────────
// Create a NEW Supabase project for email storage (separate from auth)
// Get these from: https://app.supabase.com → your EML project → Settings → API
window.EML_SUPABASE_URL      = 'https://ewlcrbkfwwaunpdanbcv.supabase.co';   // e.g. 'https://xxxx.supabase.co'
window.EML_SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV3bGNyYmtmd3dhdW5wZGFuYmN2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2NzY2MzEsImV4cCI6MjA5MjI1MjYzMX0.NzwfWut9GH-lHIYLmIj-_gn0AODif9SZ0SmiPKXZLUQ';   // anon/public key