// Dynamic Monaco language registration for CodeVerse Language (.cvl)

let monarchProviderHandle: any = null;
let completionProviderHandle: any = null;

export function registerCVLLanguage(monaco: any, mappings: Record<string, string>) {
  const languageId = 'cvl';

  // 1. Register the language if not already registered
  const langs = monaco.languages.getLanguages();
  if (!langs.some((l: any) => l.id === languageId)) {
    monaco.languages.register({ id: languageId });
  }

  // 2. Dispose of any existing providers to prevent memory leaks and duplicates
  if (monarchProviderHandle) {
    monarchProviderHandle.dispose();
  }
  if (completionProviderHandle) {
    completionProviderHandle.dispose();
  }

  // 3. Classify concepts from mappings
  const keywords: string[] = [];
  const builtins: string[] = [];
  const methods: string[] = [];
  const typeNames = ['int', 'float', 'str', 'bool', 'list', 'dict'];

  // Keywords defined by UniversalConcept
  const keywordKeys = [
    "function_def", "return", "if", "elif", "else", "for", "in", "while", "break", "continue",
    "class_def", "import", "try", "except", "finally", "and", "or", "not", "true", "false", "none"
  ];
  
  // Builtin callables
  const builtinKeys = ["print", "range", "len"];

  // Method callables
  const methodKeys = [
    "list_append", "list_remove", "contains", "dict_get", "dict_set", "dict_keys", "dict_values", "dict_delete"
  ];

  for (const k of keywordKeys) {
    if (mappings[k]) keywords.push(mappings[k]);
  }
  for (const k of builtinKeys) {
    if (mappings[k]) builtins.push(mappings[k]);
  }
  for (const k of methodKeys) {
    if (mappings[k]) methods.push(mappings[k]);
  }

  // 4. Define syntax tokenizer rules (Monarch)
  monarchProviderHandle = monaco.languages.setMonarchTokensProvider(languageId, {
    defaultToken: 'invalid',
    keywords,
    builtins,
    typeNames,
    methods,
    tokenizer: {
      root: [
        // Identifiers and custom keywords
        [/[a-zA-Z_ğüşıöçĞÜŞİÖÇ][a-zA-Z0-9_ğüşıöçĞÜŞİÖÇ]*/, {
          cases: {
            '@keywords': 'keyword',
            '@builtins': 'predefined',
            '@typeNames': 'type',
            '@methods': 'tag',
            '@default': 'identifier'
          }
        }],

        // Whitespace and comments
        { include: '@whitespace' },

        // Delimiters and brackets
        [/[{}()\[\]]/, '@brackets'],
        [/[<>=\-+*/%&|^~!:]+/, 'operator'],

        // Numbers
        [/\d*\.\d+([eE][\-+]?\d+)?/, 'number.float'],
        [/\d+/, 'number'],

        // Strings
        [/"/, { token: 'string.quote', bracket: '@open', next: '@string' }],
      ],

      string: [
        [/[^\\"]+/, 'string'],
        [/\\./, 'string.escape'],
        [/"/, { token: 'string.quote', bracket: '@close', next: '@pop' }],
      ],

      whitespace: [
        [/[ \t\r\n]+/, 'white'],
        [/#.*$/, 'comment'],
      ],
    },
  });

  // 5. Register auto-completion provider for CodeVerse keywords
  completionProviderHandle = monaco.languages.registerCompletionItemProvider(languageId, {
    provideCompletionItems: (_model: any, _position: any) => {
      const suggestions: any[] = [];

      // Add structural keywords
      for (const k of keywordKeys) {
        if (mappings[k]) {
          suggestions.push({
            label: mappings[k],
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: mappings[k],
            detail: `Keyword: ${k.replace('_', ' ')}`
          });
        }
      }

      // Add builtins (e.g. print)
      for (const b of builtinKeys) {
        if (mappings[b]) {
          suggestions.push({
            label: mappings[b],
            kind: monaco.languages.CompletionItemKind.Function,
            insertText: `${mappings[b]}($0)`,
            insertTextRules: monaco.languages.CompletionItemInsertRule.InsertAsSnippet,
            detail: `Builtin: ${b}`
          });
        }
      }

      // Add standard type names (types are NOT themed)
      for (const t of typeNames) {
        suggestions.push({
          label: t,
          kind: monaco.languages.CompletionItemKind.TypeParameter,
          insertText: t,
          detail: `Type: ${t}`
        });
      }

      // Add method calls (e.g. append)
      for (const m of methodKeys) {
        if (mappings[m]) {
          suggestions.push({
            label: mappings[m],
            kind: monaco.languages.CompletionItemKind.Method,
            insertText: mappings[m],
            detail: `Method: ${m.replace('_', ' ')}`
          });
        }
      }

      return { suggestions };
    }
  });
}
