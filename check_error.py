import traceback
try:
    import seed_vault
except Exception as e:
    with open("error.txt", "w") as f:
        f.write(traceback.format_exc())
