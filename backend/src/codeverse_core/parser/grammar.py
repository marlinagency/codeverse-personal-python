"""DSL grammar reference (EBNF).

The grammar is defined over CANONICAL keywords; themed keywords are resolved
to canonical ones by the lexer, so this grammar is theme-independent.

    program        := statement* EOF
    statement      := simple_stmt NEWLINE | compound_stmt
    simple_stmt    := return_stmt | break_stmt | continue_stmt
                    | import_stmt | assignment | expr_stmt
    return_stmt    := "return" [expr]
    import_stmt    := "import" dotted_name
    assignment     := target [":" type] "=" expr
    target         := NAME | postfix_index | postfix_attr
    expr_stmt      := expr

    compound_stmt  := func_def | class_def | if_stmt | for_stmt
                    | while_stmt | try_stmt
    func_def       := "func" NAME "(" [params] ")" [":" type-annot] block
    params         := param ("," param)*
    param          := NAME [":" type] ["=" expr]
    class_def      := "class" NAME ["(" NAME ")"] block
                      -- block body: annotated assignments (fields) and
                         func_defs (methods)
    if_stmt        := "if" expr block ("elif" expr block)* ["else" block]
    for_stmt       := "for" NAME "in" expr block
    while_stmt     := "while" expr block
    try_stmt       := "try" block ("except" [NAME] block)+ ["finally" block]
    block          := ":" NEWLINE INDENT statement+ DEDENT

    expr           := or_expr
    or_expr        := and_expr ("or" and_expr)*
    and_expr       := not_expr ("and" not_expr)*
    not_expr       := "not" not_expr | comparison
    comparison     := arith (("=="|"!="|"<"|"<="|">"|">=") arith)*
    arith          := term (("+"|"-") term)*
    term           := unary (("*"|"/"|"%") unary)*
    unary          := "-" unary | postfix
    postfix        := primary ( "(" [args] ")" | "[" expr "]"
                    | "." NAME ["(" [args] ")"] )*
    primary        := NUMBER | STRING | "true" | "false" | "none"
                    | NAME | list_lit | dict_lit | "(" expr ")"
    list_lit       := "[" [expr ("," expr)*] "]"
    dict_lit       := "{" [expr ":" expr ("," expr ":" expr)*] "}"
    type           := "int" | "float" | "str" | "bool" | "list" | "dict" | NAME
"""

BINARY_COMPARISON_OPS = frozenset({"==", "!=", "<", "<=", ">", ">="})
