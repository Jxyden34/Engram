"""Bounded exports using current project evidence, without model-generated facts."""
from datetime import datetime,timezone
import re
from app.database import connect,current_project_id
from app import reflection


def snapshot():
    with connect() as conn:
        conn.commit()
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        project=conn.execute('SELECT id,name FROM projects WHERE id=%s',(current_project_id(),)).fetchone()
        where="deleted_at IS NULL AND (valid_from IS NULL OR valid_from<=now()) AND (valid_to IS NULL OR valid_to>now())"
        total=conn.execute('SELECT count(*) AS n FROM memories WHERE '+where).fetchone()['n']
        rows=conn.execute('SELECT id,title,content,memory_type,source_ref,updated_at,metadata FROM memories WHERE '+where+' ORDER BY updated_at DESC,id LIMIT 500').fetchall()
        memories=[]
        for row in rows:
            item=dict(row);item['content_truncated']=len(item['content'])>20000;item['content']=item['content'][:20000]
            memories.append(item)
    briefs=[]
    for brief in reflection.list_briefs()[:20]:
        checked=reflection.get_brief(str(brief['id']))
        briefs.append(checked)
    decisions=[m for m in memories if m['memory_type'].lower() in {'decision','decisions'}]
    questions=[m for m in memories if m['memory_type'].lower() in {'question','open_question','task'} and (m['metadata'] or {}).get('status','open') not in {'done','closed','resolved'}]
    return {'project':dict(project),'generated_at':datetime.now(timezone.utc).isoformat(),
            'summary':f"{project['name']}: {total} current memories; {len(decisions)} decisions and {len(questions)} outstanding questions/tasks in this export.",
            'total_memories':total,'exported_memories':len(memories),'omitted_memories':max(0,total-len(memories)),
            'decisions':decisions,'outstanding_questions':questions,'briefs':briefs,'sources':memories,
            'limitations':'At most 500 current memories (20,000 characters each) and 20 saved briefs. Counts of decisions/questions describe the exported subset. Review source dates before relying on this handover.'}


def plain(value):
    # A fence longer than any user-provided backtick run cannot be closed by source content.
    value=str(value)
    fence='`'*(max((len(m.group()) for m in re.finditer(r'`+',value)),default=0)+3)
    return '\n'+fence+'text\n'+value+'\n'+fence+'\n'


def markdown(data):
    lines=['# Project handover','',plain(data['project']['name']),'',data['summary'],'',
           'Generated: '+data['generated_at'],'',data['limitations'],'']
    for heading,key in [('Decisions','decisions'),('Outstanding questions and tasks','outstanding_questions')]:
        lines+=['## '+heading,'']
        if not data[key]:lines+=['No matching memories in the exported subset.','']
        for memory in data[key]:lines += [plain(memory['title']),plain(memory['content']),'Source ID: '+str(memory['id']),'']
    lines+=['## Saved project briefs','']
    for brief in data['briefs']:
        lines += [plain(brief['title']),'Status: '+brief['status']]
        if brief['status']=='current':
            for claim in brief['claims']:lines += [plain(claim['text'])]
        else:lines += ['Review this brief in Engram before using its conclusions.']
        lines+=['']
    lines+=['## Source memories','']
    for source in data['sources']:
        lines += [plain(source['title']),'ID: '+str(source['id']),'Updated: '+str(source['updated_at']),plain(source['content'])]
        if source['source_ref']:lines += ['Original reference:',plain(source['source_ref'])]
        if source['content_truncated']:lines += ['Content truncated; open the original memory for the remainder.']
        lines+=['']
    return '\n'.join(lines)
