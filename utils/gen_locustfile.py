import os
import shutil

# Set the directory where the .py files are located
directory = "./locustfiles"

replace_content = ("TweetGen", "WikiGen")
replace_name = "tweet", "wiki"


# Iterate through all the files in the directory
for filename in os.listdir(directory):
  # Check if the file is a .py file and has "tweet" in the name
  if filename.endswith(".py") and replace_name[0] in filename:
    # Read the contents of the file
    with open(os.path.join(directory, filename), "r") as f:
      contents = f.read()
    # Replace "TweetGen" with "WikiGen"
    contents = contents.replace(*replace_content)
    # Create the new filename with "wiki" instead of "tweet"
    new_filename = filename.replace(*replace_name)
    # Write the modified contents to the new file
    with open(os.path.join(directory, new_filename), "w") as f:
      f.write(contents)
