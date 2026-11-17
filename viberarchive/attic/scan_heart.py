import os

root_folder = r"D:\ViberRecovery\files\files"

keyword = "laugh"

for root, dirs, files in os.walk(root_folder):
    for file in files:
        if keyword.lower() in file.lower():
            print(os.path.join(root, file))