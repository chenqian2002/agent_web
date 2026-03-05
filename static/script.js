// 首页搜索加载动画
const searchForm = document.querySelector('.search-box');
if (searchForm) {
    searchForm.addEventListener('submit', function() {
        document.getElementById('loading').classList.add('show');
    });
}

// 聊天历史
let chatHistory = [];

// 发送消息
function sendMessage() {
    const input = document.getElementById('user-input');
    const message = input.value.trim();
    if (!message) return;
    
    // 显示用户消息
    addMessage(message, 'user');
    input.value = '';
    
    // 显示加载中
    const loadingDiv = addMessage('⏳ 思考中...', 'bot');
    
    // 发送到后端
    fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            message: message,
            history: chatHistory
        })
    })
    .then(response => response.json())
    .then(data => {
        // 移除加载提示
        loadingDiv.remove();
        // 显示 AI 回复
        addMessage(data.reply, 'bot');
        // 保存历史
        chatHistory.push({role: 'user', content: message});
        chatHistory.push({role: 'assistant', content: data.reply});
    })
    .catch(error => {
        loadingDiv.remove();
        addMessage('❌ 网络错误，请重试', 'bot');
    });
}

// 添加消息到界面
function addMessage(text, type) {
    const messagesDiv = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.innerHTML = `<div class="message-content">${text}</div>`;
    messagesDiv.appendChild(messageDiv);
    // 滚动到底部
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return messageDiv;
}

// 按回车发送
function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

async function uploadAndAsk() {
    const fileInput = document.getElementById("docFile");
    //获取用户问题value，trim()去除空格处理
    const q = document.getElementById("question").value.trim();
    if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
        showToast("請先選擇 .txt 文件", "error");
        return;
    }
    if (!q) {
        showToast("請先輸入問題", "error");
        return;
    }
    const file = fileInput.files[0];
    const form = new FormData();
    form.append("file", file);
    form.append("question", q);
    answerEl.textContent = "正在上傳並分析文件…";
    //classList添加class=loading
    answerEl.classList.add("loading");
    //控制元素显示/隐藏
    sourcesWrap.style.display = "none";
    sourcesEl.innerHTML = "";
    try{
        //fetch 是浏览器提供的 发送 HTTP 请求的函数。
        const resp =await fetch("/api/docsqa/upload", {
            method: "POST",
            body: form
        });
        //把包裹里的内容拆开，并翻译成 JSON 格式的数据
        const data = await resp.json();
        //textContent这是在修改这个网页元素里的纯文字内容
//data.answer：从刚才解析好的 data（也就是你上一问拿到的 JSON 数据）中，
// 提取出名字叫 answer 的那个属性的值。
//如果ata.answer 有正常内容，就用左边；如果左边是“无效的”
// （比如不存在、是 null、或者为空字符串 ""），就强制使用右边的值。
        answerEl.textContent = data.answer || "(無回應)";
        answerEl.classList.remove("loading");
        sourcesWrap.style.display = "";
        if (data.sources && data.sources.length > 0){
            //将sourcesWrap显示出来
            sourcesWrap.style.display = "block";
//innerHTML 允许你往网页里塞真正的 HTML 标签,data.sources：
// 从服务器解析出来的 data 里，提取名叫 sources 的数据。它.map(...)：这是 JavaScript 处理数组的“变形器”。
// 它的作用是遍历数组里的每一项数据，并按你的要求把它们转换成另一种格式
            sourcesEl.innerHTML=data.sources.map(
                function(s,i){
                    //这里的s.source是原始文件名，如果没有就用“上傳文件”代替。
                    //s.content是文件内容，如果没有就用空字符串""代替。
                    //在source-item中加入序号，文件名和内容。
                    return '<div class="source-item"><strong>[' + (i + 1) + '] ' 
                    + (s.source || "上傳文件") + '</strong>\n' +
                    (s.content || "") + '</div>';
//join("") 后，就能把数组里的所有代码无缝拼成一整段长长的 HTML 字符串，
// 这样网页渲染出来就完美无瑕了。
                }).join("");
        }
    }catch (err) {
        answerEl.textContent="发生错误"+err.message;
        answerEl.classList.remove("loading");
        showToast("請求失敗", "error");
    }
}
// 切换窗口显示/隐藏
function toggleChatWidget() {
    const win = document.getElementById('chat-widget-window');
    if (win.style.display === 'none' || win.style.display === '') {
        //是把 win 这个 HTML 元素显示出来，并且让它变成 Flex 布局，方便内部子元素进行灵活排列。
        win.style.display = 'flex';
    }else {
        win.style.display = 'none';
    }
}
// 独立的聊天历史，避免和页面其他功能冲突
let widgetHistory = [];
function sendWidgetMessage() {
    const input = document.getElementById('widget-input');
    const msg = input.value.trim();
    if (!msg) return;

    // 1. 显示用户消息
    addWidgetMsg(msg, 'user');
    input.value = '';

    // 2. 显示 "思考中"
    const loadingId = addWidgetMsg('🤖 正在思考...', 'bot');

    // 3. 发送给后端
    fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: msg,
            history: widgetHistory
        })
    })
    .then(res => res.json())
    .then(data => {
        // 移除加载提示
        const loadingDiv = document.getElementById(loadingId);
        if(loadingDiv) loadingDiv.remove();

        // 显示 AI 回复
        if (data.reply) {
            addWidgetMsg(data.reply, 'bot');
            // 更新历史
            widgetHistory.push({role: 'user', content: msg});
            widgetHistory.push({role: 'assistant', content: data.reply});
        } else {
            addWidgetMsg("⚠️ 服务器未返回有效内容", 'bot');
        }
    })
    .catch(err => {
        console.error("Fetch 错误:", err);
        const loadingDiv = document.getElementById(loadingId);
        if(loadingDiv) loadingDiv.innerText = "❌ 网络连接错误";
    });
}
// 辅助函数：添加消息到 DOM
function addWidgetMsg(text, role) {
    const box = document.getElementById('widget-messages');
    const div = document.createElement('div');
    const id = 'msg-' + new Date().getTime();
    div.id = id;
    div.className = `message ${role}`;
    div.innerHTML = `<div class="message-content">${text}</div>`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return id;

}
// 回车发送
function handleWidgetKeyPress(e) {
    if (e.key === 'Enter') sendWidgetMessage();
}