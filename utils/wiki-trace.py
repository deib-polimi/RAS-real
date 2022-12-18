import csv
import sys

# generate trace from http://www.wikibench.eu/

file =  sys.argv[1]
# Open the CSV file in read mode
with open(file, 'r') as csv_file:
    with open('wiki.csv', 'w', newline='') as csv_file2:
        # Create a CSV reader object
        reader = csv.reader(csv_file, delimiter=" ")
        writer = csv.writer(csv_file2)
 
        ts = []
        while True:
            try:
                row = next(reader)
                timestamp = int(float(row[1])*100)
                ts.append(timestamp)
            except StopIteration:
                break
            except:
                continue
        ts = sorted(ts)
        second = None
        users = 0
        for timestamp in ts:
            if second == None:
                second = timestamp
            elif second != timestamp:
                writer.writerow((users,))
                users = 0
                second = timestamp
            users += 1
           
        writer.writerow((users,))
