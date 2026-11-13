"""Environment of test165 (Python version of .env-packaging)."""


def module_final_step(ctx):
    _, variant, _, _ = ctx.module_ref("metaagg")
    tvdir = ctx.target_dir("metaagg", variant)
    print(f"R m:{ctx.module} v:{ctx.variant} d:{ctx.depends_kind} m:{ctx.is_meta} "
          f"a:{ctx.is_aggregated} i:{ctx.is_up_to_date}")
    print(f"Copy {ctx.prefix}")
    print(f"To {tvdir}/app")
