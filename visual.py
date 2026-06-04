import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

df = pd.read_csv('jsp/results.csv')

fig, ax = plt.subplots(figsize=(16, 8))

unique_jobs = sorted(df['Job'].unique())
cmap = plt.get_cmap('gist_rainbow', len(unique_jobs))
job_colors = {job: cmap(i) for i, job in enumerate(unique_jobs)}

for _, row in df.iterrows():
    job_id = row['Job']
    op_id = row['Operation']
    machine_id = row['Machine']

    ax.broken_barh([(row['Start'], row['Duration'])], (machine_id - 0.4, 0.8), 
        facecolors=job_colors[job_id],
        edgecolor='black',
        alpha=0.8
    )
    
    ax.text(
        row['Start'] + row['Duration']/2, 
        machine_id, 
        f"O_{int(job_id)}_{int(op_id)}", 
        va='center', ha='center', color='white', fontweight='bold', fontsize=9
    )


ax.set_xlabel('Time')
ax.set_ylabel('Machine ID')
ax.set_yticks(df['Machine'].unique())
ax.grid(True, linestyle='--', alpha=0.6)

plt.tight_layout()
plt.show()






# import pandas as pd
# import matplotlib.pyplot as plt

# df = pd.read_csv('jsp/results.csv')

# fig, ax = plt.subplots(figsize=(10, 6))

# for i, row in df.iterrows():
#     # broken_barh: [(start_time, duration)], (y_position, row_thickness)
#     ax.broken_barh([(row['Start'], row['Duration'])], (row['Job']-0.4, 0.8), facecolors=('tab:blue'))

# ax.set_xlabel('Time')
# ax.set_ylabel('Job ID')
# ax.set_yticks(df['Job'].unique())
# ax.grid(True, linestyle='--', alpha=0.6)

# plt.tight_layout()
# plt.show()



