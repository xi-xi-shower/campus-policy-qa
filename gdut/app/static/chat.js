const input = document.getElementById('question-input');
const messages = document.getElementById('messages');
const welcome = document.getElementById('welcome');
const scrollArea = document.getElementById('content-scroll');
const sendButton = document.getElementById('send-button');
const dialog = document.getElementById('detail-dialog');
let history = [], busy = false, controller = null, generation = 0;

function showDialog(title, paragraphs) {
  document.getElementById('dialog-title').textContent = title;
  const body = document.getElementById('dialog-content');
  body.replaceChildren();
  paragraphs.forEach(text => {
    const p = document.createElement('p'); p.textContent = text; body.append(p);
  });
  dialog.showModal();
}
function updateInput() { sendButton.disabled = busy || !input.value.trim(); }
async function ask(question) {
  question = question.trim();
  if (!question || busy) return;
  if (question.length > 2000) return;
  const turn = generation;
  busy = true; updateInput(); welcome.hidden = true;
  const user = document.createElement('div');
  user.className = 'message user-message'; user.textContent = question; messages.append(user);
  const answer = document.createElement('article'); answer.className = 'message assistant-message';
  const title = document.createElement('div'); title.className = 'assistant-header'; title.textContent = '校园助手';
  const body = document.createElement('div'); body.className = 'answer-body'; body.style.whiteSpace = 'pre-wrap';
  body.textContent = '正在检索政策并整理回答…'; answer.append(title, body); messages.append(answer);
  document.querySelector('#current-chat span').textContent = question;
  input.value = ''; user.scrollIntoView({block:'start'});
  controller = new AbortController();
  const timer = setTimeout(() => controller?.abort(), 150000);
  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({message:question, history:history.slice(-6)}), signal:controller.signal,
    });
    const result = await response.json();
    if (generation !== turn) return;
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '请求失败，请稍后重试。');
    body.textContent = result.answer;
    history.push({role:'user',content:question},{role:'assistant',content:result.answer});
    history = history.slice(-6);
    if (result.sources.length) {
      const label = document.createElement('div'); label.className = 'source-label';
      label.textContent = '本轮检索片段（结论依据请核对回答中的引用）'; answer.append(label);
      result.sources.forEach(source => {
        const button = document.createElement('button'); button.className = 'source-button';
        button.textContent = source.label || (source.file_type === 'md'
          ? `${source.filename}，章节：${source.section}`
          : `${source.filename}，第 ${source.page} 页`);
        button.addEventListener('click', () => showDialog(button.textContent, [source.text]));
        answer.append(button);
      });
    }
  } catch (error) {
    if (generation !== turn) return;
    body.textContent = error.name === 'AbortError' ? '请求超时，请稍后重试。' :
      (error instanceof TypeError ? '无法连接问答服务，请检查服务是否启动。' : error.message);
    input.value = question;
  } finally {
    clearTimeout(timer);
    if (generation === turn) { busy = false; controller = null; updateInput(); }
  }
}
function newChat() {
  generation++; controller?.abort(); controller = null; busy = false; history = [];
  messages.replaceChildren(); welcome.hidden = false;
  document.querySelector('#current-chat span').textContent = '开始一段新对话';
  input.value = ''; updateInput(); scrollArea.scrollTop = 0; input.focus();
}
document.getElementById('question-form').addEventListener('submit', event => {event.preventDefault(); ask(input.value);});
input.addEventListener('input', updateInput);
input.addEventListener('keydown', event => {
  if(event.key === 'Enter' && !event.shiftKey && !event.isComposing) {event.preventDefault(); ask(input.value);}
});
document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => ask(button.dataset.question)));
['new-chat','mobile-new'].forEach(id => document.getElementById(id).addEventListener('click', newChat));
document.getElementById('current-chat').addEventListener('click', () => {scrollArea.scrollTop = scrollArea.scrollHeight; input.focus();});
document.getElementById('about').addEventListener('click', () => showDialog('关于校园助手', [
  '基于已导入的 PDF 和 Markdown 政策检索回答。PDF 引用文件页序，Markdown 引用章节。未覆盖的问题将提示暂无相关政策。',
  '追问使用最近 3 轮完整对话。对话仅保留在当前页面，刷新或新建对话后清空。',
  '点击回答下方的来源可核对本轮检索原文。Gradio 聊天入口：/gradio。',
]));
['close-dialog','confirm-dialog'].forEach(id => document.getElementById(id).addEventListener('click', () => dialog.close()));
document.addEventListener('keydown', event => {
  if(dialog.open) return;
  if((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {event.preventDefault(); input.focus();}
  if((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === 'o') {event.preventDefault(); newChat();}
});
