/** One completion candidate for a command argument (client + suggest route). */
export interface CommandSuggestion {
  value: string;
  label: string;
  subtitle?: string;
}
