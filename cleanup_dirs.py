#!/usr/bin/env python3
import shutil
import os

dirs_to_remove = ['api', 'agent']

for dir_name in dirs_to_remove:
    if os.path.exists(dir_name):
        try:
            shutil.rmtree(dir_name)
            print(f"Successfully removed {dir_name}/")
        except Exception as e:
            print(f"Failed to remove {dir_name}/: {e}")
    else:
        print(f"{dir_name}/ does not exist")

print("Cleanup completed.")