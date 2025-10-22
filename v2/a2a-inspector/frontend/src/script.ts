import {io} from 'socket.io-client';
import {marked} from 'marked';
import DOMPurify from 'dompurify';

interface AgentResponseEvent {
  kind: 'task' | 'status-update' | 'artifact-update' | 'message';
  id: string;
  contextId?: string;
  error?: string;
  status?: {
    state: string;
    message?: {parts?: {text?: string}[]};
  };
  artifact?: {
    parts?: (
      | {file?: {uri: string; mimeType: string}}
      | {text?: string}
      | {data?: object}
    )[];
  };
  parts?: {text?: string}[];
  validation_errors: string[];
}

interface DebugLog {
  type: 'request' | 'response' | 'error' | 'validation_error';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any;
  id: string;
}

// Declare hljs global from CDN
declare global {
  interface Window {
    hljs: {
      highlightElement: (element: HTMLElement) => void;
    };
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const socket = io();

  const INITIALIZATION_TIMEOUT_MS = 10000;
  const MAX_LOGS = 500;

  const connectBtn = document.getElementById(
    'connect-btn',
  ) as HTMLButtonElement;
  const agentCardUrlInput = document.getElementById(
    'agent-card-url',
  ) as HTMLInputElement;
  const httpHeadersToggle = document.getElementById(
    'http-headers-toggle',
  ) as HTMLElement;
  const httpHeadersContent = document.getElementById(
    'http-headers-content',
  ) as HTMLElement;
  const headersList = document.getElementById('headers-list') as HTMLElement;
  const addHeaderBtn = document.getElementById(
    'add-header-btn',
  ) as HTMLButtonElement;
  const messageMetadataToggle = document.getElementById(
    'message-metadata-toggle',
  ) as HTMLElement;
  const messageMetadataContent = document.getElementById(
    'message-metadata-content',
  ) as HTMLElement;
  const metadataList = document.getElementById('metadata-list') as HTMLElement;
  const addMetadataBtn = document.getElementById(
    'add-metadata-btn',
  ) as HTMLButtonElement;
  const collapsibleHeader = document.querySelector(
    '.collapsible-header',
  ) as HTMLElement;
  const collapsibleContent = document.querySelector(
    '.collapsible-content',
  ) as HTMLElement;
  const agentCardCodeContent = document.getElementById(
    'agent-card-content',
  ) as HTMLElement;
  const validationErrorsContainer = document.getElementById(
    'validation-errors',
  ) as HTMLElement;
  const chatInput = document.getElementById('chat-input') as HTMLInputElement;
  const sendBtn = document.getElementById('send-btn') as HTMLButtonElement;
  const chatMessages = document.getElementById('chat-messages') as HTMLElement;
  const debugConsole = document.getElementById('debug-console') as HTMLElement;
  const debugHandle = document.getElementById('debug-handle') as HTMLElement;
  const debugContent = document.getElementById('debug-content') as HTMLElement;
  const clearConsoleBtn = document.getElementById(
    'clear-console-btn',
  ) as HTMLButtonElement;
  const toggleConsoleBtn = document.getElementById(
    'toggle-console-btn',
  ) as HTMLButtonElement;
  const jsonModal = document.getElementById('json-modal') as HTMLElement;
  const modalJsonContent = document.getElementById(
    'modal-json-content',
  ) as HTMLPreElement;
  const modalCloseBtn = document.querySelector(
    '.modal-close-btn',
  ) as HTMLElement;

  let isResizing = false;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rawLogStore: Record<string, Record<string, any>> = {};
  const messageJsonStore: {[key: string]: AgentResponseEvent} = {};
  const logIdQueue: string[] = [];
  let initializationTimeout: ReturnType<typeof setTimeout>;
  let isProcessingLogQueue = false;

  debugHandle.addEventListener('mousedown', (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target === debugHandle || target.tagName === 'SPAN') {
      isResizing = true;
      document.body.style.userSelect = 'none';
      document.body.style.pointerEvents = 'none';
    }
  });

  window.addEventListener('mousemove', (e: MouseEvent) => {
    if (!isResizing) return;
    const newHeight = window.innerHeight - e.clientY;
    if (newHeight > 40 && newHeight < window.innerHeight * 0.9) {
      debugConsole.style.height = `${newHeight}px`;
    }
  });

  window.addEventListener('mouseup', () => {
    isResizing = false;
    document.body.style.userSelect = '';
    document.body.style.pointerEvents = '';
  });

  collapsibleHeader.addEventListener('click', () => {
    collapsibleHeader.classList.toggle('collapsed');
    collapsibleContent.classList.toggle('collapsed');
    collapsibleContent.style.overflow = 'hidden';
  });

  collapsibleContent.addEventListener('transitionend', () => {
    if (!collapsibleContent.classList.contains('collapsed')) {
      collapsibleContent.style.overflow = 'auto';
    }
  });

  // Generic function to setup toggle functionality
  function setupToggle(
    toggleElement: HTMLElement,
    contentElement: HTMLElement,
  ) {
    if (!toggleElement || !contentElement) return;
    toggleElement.addEventListener('click', () => {
      const isExpanded = contentElement.classList.toggle('expanded');
      const toggleIcon = toggleElement.querySelector('.toggle-icon');
      if (toggleIcon) {
        toggleIcon.textContent = isExpanded ? '▼' : '►';
      }
    });
  }

  // Setup toggle functionality for both sections
  setupToggle(httpHeadersToggle, httpHeadersContent);
  setupToggle(messageMetadataToggle, messageMetadataContent);

  // Add a new, empty header field when the button is clicked
  addHeaderBtn.addEventListener('click', () => addHeaderField());

  // Add a new, empty metadata field when the button is clicked
  addMetadataBtn.addEventListener('click', () => addMetadataField());

  // Generic function to setup remove item event listeners
  function setupRemoveItemListener(
    listElement: HTMLElement,
    removeBtnSelector: string,
    itemSelector: string,
  ) {
    listElement.addEventListener('click', event => {
      const removeBtn = (event.target as HTMLElement).closest(
        removeBtnSelector,
      );
      if (removeBtn) {
        removeBtn.closest(itemSelector)?.remove();
      }
    });
  }

  // Setup remove item listeners
  setupRemoveItemListener(headersList, '.remove-header-btn', '.header-item');
  setupRemoveItemListener(
    metadataList,
    '.remove-metadata-btn',
    '.metadata-item',
  );

  // Generic function to add key-value fields
  function addKeyValueField(
    list: HTMLElement,
    classes: {item: string; key: string; value: string; removeBtn: string},
    placeholders: {key: string; value: string},
    removeLabel: string,
    key = '',
    value = '',
  ) {
    const itemHTML = `
      <div class="${classes.item}">
        <input type="text" class="${classes.key}" placeholder="${placeholders.key}" value="${key}">
        <input type="text" class="${classes.value}" placeholder="${placeholders.value}" value="${value}">
        <button type="button" class="${classes.removeBtn}" aria-label="${removeLabel}">×</button>
      </div>
    `;
    list.insertAdjacentHTML('beforeend', itemHTML);
  }

  // Function to add a new header field
  function addHeaderField(name = '', value = '') {
    addKeyValueField(
      headersList,
      {
        item: 'header-item',
        key: 'header-name',
        value: 'header-value',
        removeBtn: 'remove-header-btn',
      },
      {key: 'Header Name', value: 'Header Value'},
      'Remove header',
      name,
      value,
    );
  }

  // Function to add a new metadata field
  function addMetadataField(key = '', value = '') {
    addKeyValueField(
      metadataList,
      {
        item: 'metadata-item',
        key: 'metadata-key',
        value: 'metadata-value',
        removeBtn: 'remove-metadata-btn',
      },
      {key: 'Metadata Key', value: 'Metadata Value'},
      'Remove metadata',
      key,
      value,
    );
  }

  // Generic function to collect key-value pairs from the DOM
  function getKeyValuePairs(
    list: HTMLElement,
    itemSelector: string,
    keySelector: string,
    valueSelector: string,
  ): Record<string, string> {
    const items = list.querySelectorAll(itemSelector);
    return Array.from(items).reduce(
      (acc, item) => {
        const keyInput = item.querySelector(keySelector) as HTMLInputElement;
        const valueInput = item.querySelector(
          valueSelector,
        ) as HTMLInputElement;
        const key = keyInput?.value.trim();
        const value = valueInput?.value.trim();
        if (key && value) {
          acc[key] = value;
        }
        return acc;
      },
      {} as Record<string, string>,
    );
  }

  // Function to collect all headers
  function getCustomHeaders(): Record<string, string> {
    return getKeyValuePairs(
      headersList,
      '.header-item',
      '.header-name',
      '.header-value',
    );
  }

  // Function to collect all metadata
  function getMessageMetadata(): Record<string, string> {
    return getKeyValuePairs(
      metadataList,
      '.metadata-item',
      '.metadata-key',
      '.metadata-value',
    );
  }

  clearConsoleBtn.addEventListener('click', () => {
    debugContent.innerHTML = '';
    Object.keys(rawLogStore).forEach(key => delete rawLogStore[key]);
    logIdQueue.length = 0;
  });

  toggleConsoleBtn.addEventListener('click', () => {
    const isHidden = debugConsole.classList.toggle('hidden');
    toggleConsoleBtn.textContent = isHidden ? 'Show' : 'Hide';
  });

  modalCloseBtn.addEventListener('click', () =>
    jsonModal.classList.add('hidden'),
  );
  jsonModal.addEventListener('click', (e: MouseEvent) => {
    if (e.target === jsonModal) {
      jsonModal.classList.add('hidden');
    }
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const showJsonInModal = (jsonData: any) => {
    if (jsonData) {
      let jsonString = JSON.stringify(jsonData, null, 2);
      jsonString = jsonString.replace(
        /"method": "([^"]+)"/g,
        '<span class="json-highlight">"method": "$1"</span>',
      );
      modalJsonContent.innerHTML = jsonString;
      jsonModal.classList.remove('hidden');
    }
  };

  connectBtn.addEventListener('click', async () => {
    let agentCardUrl = agentCardUrlInput.value.trim();
    if (!agentCardUrl) {
      alert('Please enter an agent card URL.');
      return;
    }

    // If no protocol is specified, prepend http://
    if (!/^[a-zA-Z]+:\/\//.test(agentCardUrl)) {
      agentCardUrl = 'http://' + agentCardUrl;
    }

    // Validate that the URL uses http or https protocol
    try {
      const url = new URL(agentCardUrl);
      if (url.protocol !== 'http:' && url.protocol !== 'https:') {
        throw new Error('Protocol must be http or https.');
      }
    } catch (error) {
      alert(
        'Invalid URL. Please enter a valid URL starting with http:// or https://.',
      );
      return;
    }

    agentCardCodeContent.textContent = '';
    validationErrorsContainer.innerHTML =
      '<div class="loader"></div><p class="placeholder-text">Fetching Agent Card...</p>';
    chatInput.disabled = true;
    sendBtn.disabled = true;

    // Get custom headers
    const customHeaders = getCustomHeaders();

    // Prepare request headers
    const requestHeaders = {
      'Content-Type': 'application/json',
      ...customHeaders,
    };

    try {
      const response = await fetch('/agent-card', {
        method: 'POST',
        headers: requestHeaders,
        body: JSON.stringify({url: agentCardUrl, sid: socket.id}),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || `HTTP error! status: ${response.status}`);
      }

      agentCardCodeContent.textContent = JSON.stringify(data.card, null, 2);
      if (window.hljs) {
        window.hljs.highlightElement(agentCardCodeContent);
      } else {
        console.warn('highlight.js not loaded. Syntax highlighting skipped.');
      }

      validationErrorsContainer.innerHTML =
        '<p class="placeholder-text">Initializing client session...</p>';

      initializationTimeout = setTimeout(() => {
        validationErrorsContainer.innerHTML =
          '<p class="error-text">Error: Client initialization timed out.</p>';
        chatInput.disabled = true;
        sendBtn.disabled = true;
      }, INITIALIZATION_TIMEOUT_MS);

      socket.emit('initialize_client', {
        url: agentCardUrl,
        customHeaders: customHeaders,
      });

      if (data.validation_errors.length > 0) {
        validationErrorsContainer.innerHTML = `<h3>Validation Errors</h3><ul>${data.validation_errors.map((e: string) => `<li>${e}</li>`).join('')}</ul>`;
      } else {
        validationErrorsContainer.innerHTML =
          '<p style="color: green;">Agent card is valid.</p>';
      }
    } catch (error) {
      clearTimeout(initializationTimeout);
      validationErrorsContainer.innerHTML = `<p style="color: red;">Error: ${(error as Error).message}</p>`;
      chatInput.disabled = true;
      sendBtn.disabled = true;
    }
  });

  socket.on(
    'client_initialized',
    (data: {status: string; message?: string}) => {
      clearTimeout(initializationTimeout);
      if (data.status === 'success') {
        chatInput.disabled = false;
        sendBtn.disabled = false;
        chatMessages.innerHTML =
          '<p class="placeholder-text">Ready to chat.</p>';
        debugContent.innerHTML = '';
        Object.keys(rawLogStore).forEach(key => delete rawLogStore[key]);
        logIdQueue.length = 0;
        Object.keys(messageJsonStore).forEach(
          key => delete messageJsonStore[key],
        );
      } else {
        validationErrorsContainer.innerHTML = `<p style="color: red;">Error initializing client: ${data.message}</p>`;
      }
    },
  );

  let contextId: string | null = null;

  const sendMessage = () => {
    const messageText = chatInput.value;
    if (messageText.trim() && !chatInput.disabled) {
      // Sanitize the user's input before doing anything else
      const sanitizedMessage = DOMPurify.sanitize(messageText);

      // Optional but recommended: prevent sending messages that are empty after sanitization
      if (!sanitizedMessage.trim()) {
        chatInput.value = '';
        return;
      }

      const messageId = `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const metadata = getMessageMetadata();

      // Use the sanitized message when displaying it locally
      appendMessage('user', sanitizedMessage, messageId);

      // Use the sanitized message when sending it to the server, along with metadata
      socket.emit('send_message', {
        message: sanitizedMessage,
        id: messageId,
        contextId,
        metadata,
      });
      chatInput.value = '';
    }
  };

  sendBtn.addEventListener('click', sendMessage);
  chatInput.addEventListener('keypress', (e: KeyboardEvent) => {
    if (e.key === 'Enter') sendMessage();
  });

  socket.on('agent_response', (event: AgentResponseEvent) => {
    const displayMessageId = `display-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    messageJsonStore[displayMessageId] = event;

    const validationErrors = event.validation_errors || [];

    if (event.error) {
      const messageHtml = `<span class="kind-chip kind-chip-error">error</span> Error: ${DOMPurify.sanitize(event.error)}`;
      appendMessage(
        'agent error',
        messageHtml,
        displayMessageId,
        true,
        validationErrors,
      );
      return;
    }

    if (event.contextId) contextId = event.contextId;

    switch (event.kind) {
      case 'task':
        if (event.status) {
          const messageHtml = `<span class="kind-chip kind-chip-task">${event.kind}</span> Task created with status: ${DOMPurify.sanitize(event.status.state)}`;
          appendMessage(
            'agent progress',
            messageHtml,
            displayMessageId,
            true,
            validationErrors,
          );
        }
        break;
      case 'status-update': {
        const statusText = event.status?.message?.parts?.[0]?.text;
        if (statusText) {
          const renderedContent = DOMPurify.sanitize(
            marked.parse(statusText) as string,
          );
          const messageHtml = `<span class="kind-chip kind-chip-status-update">${event.kind}</span> Server responded with: ${renderedContent}`;
          appendMessage(
            'agent progress',
            messageHtml,
            displayMessageId,
            true,
            validationErrors,
          );
        }
        break;
      }
      case 'artifact-update':
        event.artifact?.parts?.forEach(p => {
          let content: string | null = null;

          if ('text' in p && p.text) {
            content = DOMPurify.sanitize(marked.parse(p.text) as string);
          } else if ('file' in p && p.file) {
            const {uri, mimeType} = p.file;
            const sanitizedMimeType = DOMPurify.sanitize(mimeType);
            const sanitizedUri = DOMPurify.sanitize(uri);
            content = `File received (${sanitizedMimeType}): <a href="${sanitizedUri}" target="_blank" rel="noopener noreferrer">Open Link</a>`;
          } else if ('data' in p && p.data) {
            content = `<pre><code>${DOMPurify.sanitize(JSON.stringify(p.data, null, 2))}</code></pre>`;
          }

          if (content !== null) {
            const kindChip = `<span class="kind-chip kind-chip-artifact-update">${event.kind}</span>`;
            const messageHtml = `${kindChip} ${content}`;

            appendMessage(
              'agent',
              messageHtml,
              displayMessageId,
              true,
              validationErrors,
            );
          }
        });
        break;
      case 'message': {
        const textPart = event.parts?.find(p => p.text);
        if (textPart && textPart.text) {
          const renderedContent = DOMPurify.sanitize(
            marked.parse(textPart.text) as string,
          );
          const messageHtml = `<span class="kind-chip kind-chip-message">${event.kind}</span> ${renderedContent}`;
          appendMessage(
            'agent',
            messageHtml,
            displayMessageId,
            true,
            validationErrors,
          );
        }
        break;
      }
    }
  });

  function processLogQueue() {
    if (isProcessingLogQueue) return;
    isProcessingLogQueue = true;

    while (logIdQueue.length > MAX_LOGS) {
      const oldestKey = logIdQueue.shift();
      if (
        oldestKey &&
        Object.prototype.hasOwnProperty.call(rawLogStore, oldestKey)
      ) {
        delete rawLogStore[oldestKey];
      }
    }
    isProcessingLogQueue = false;
  }

  socket.on('debug_log', (log: DebugLog) => {
    const logEntry = document.createElement('div');
    const timestamp = new Date().toLocaleTimeString();

    let jsonString = JSON.stringify(log.data, null, 2);
    jsonString = jsonString.replace(
      /"method": "([^"]+)"/g,
      '<span class="json-highlight">"method": "$1"</span>',
    );

    logEntry.className = `log-entry log-${log.type}`;
    logEntry.innerHTML = `
            <div>
                <span class="log-timestamp">${timestamp}</span>
                <strong>${log.type.toUpperCase()}</strong>
            </div>
            <pre>${jsonString}</pre>
        `;
    debugContent.appendChild(logEntry);

    if (!rawLogStore[log.id]) {
      rawLogStore[log.id] = {};
    }
    rawLogStore[log.id][log.type] = log.data;
    logIdQueue.push(log.id);
    setTimeout(processLogQueue, 0);
    debugContent.scrollTop = debugContent.scrollHeight;
  });

  function appendMessage(
    sender: string,
    content: string,
    messageId: string,
    isHtml = false,
    validationErrors: string[] = [],
  ) {
    const placeholder = chatMessages.querySelector('.placeholder-text');
    if (placeholder) placeholder.remove();

    const messageElement = document.createElement('div');
    messageElement.className = `message ${sender.replace(' ', '-')}`;

    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';

    if (isHtml) {
      messageContent.innerHTML = content;
    } else {
      messageContent.textContent = content;
    }

    messageElement.appendChild(messageContent);

    const statusIndicator = document.createElement('span');
    statusIndicator.className = 'validation-status';
    if (sender !== 'user') {
      if (validationErrors.length > 0) {
        statusIndicator.classList.add('invalid');
        statusIndicator.textContent = '⚠️';
        statusIndicator.title = validationErrors.join('\n');
      } else {
        statusIndicator.classList.add('valid');
        statusIndicator.textContent = '✅';
        statusIndicator.title = 'Message is compliant';
      }
      messageElement.appendChild(statusIndicator);
    }

    messageElement.addEventListener('click', (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName !== 'A') {
        const jsonData =
          sender === 'user'
            ? rawLogStore[messageId]?.request
            : messageJsonStore[messageId];
        showJsonInModal(jsonData);
      }
    });

    chatMessages.appendChild(messageElement);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  // ============================================================================
  // Task Dashboard
  // ============================================================================

  interface Task {
    id: string;
    contextId: string;
    status: {
      state: string;
      timestamp?: string;
      message?: {parts?: {text?: string}[]};
    };
    artifacts?: {
      name?: string;
      description?: string;
      parts?: ({text?: string} | {file?: {uri: string}} | {data?: object})[];
    }[];
    history?: {
      role: string;
      parts?: {text?: string}[];
    }[];
    metadata?: Record<string, unknown>;
  }

  interface TaskStats {
    total: number;
    active: number;
    submitted: number;
    working: number;
    completed: number;
    failed: number;
    cancelled: number;
    active_contexts: number;
  }

  class TaskDashboard {
    private tasks: Map<string, Task> = new Map();
    private currentAgentUrl: string | null = null;
    private currentPage = 0;
    private limit = 50;
    private filters = {
      state: '',
      contextId: '',
    };

    constructor() {
      this.initializeEventListeners();
      this.setupSocketListeners();
    }

    private initializeEventListeners() {
      // Tab navigation
      const chatTab = document.getElementById('chat-tab');
      const tasksTab = document.getElementById('tasks-tab');
      const chatView = document.getElementById('chat-view');
      const tasksView = document.getElementById('tasks-view');

      chatTab?.addEventListener('click', () => {
        chatTab.classList.add('active');
        tasksTab?.classList.remove('active');
        chatView?.classList.add('active');
        chatView?.classList.remove('hidden');
        tasksView?.classList.add('hidden');
        tasksView?.classList.remove('active');
      });

      tasksTab?.addEventListener('click', () => {
        tasksTab.classList.add('active');
        chatTab?.classList.remove('active');
        tasksView?.classList.add('active');
        tasksView?.classList.remove('hidden');
        chatView?.classList.add('hidden');
        chatView?.classList.remove('active');
        // Load tasks when switching to tasks view
        this.loadTasks();
      });

      // Filter controls
      document.getElementById('filter-state')?.addEventListener('change', (e) => {
        this.filters.state = (e.target as HTMLSelectElement).value;
        this.currentPage = 0;
        this.loadTasks();
      });

      document.getElementById('filter-context')?.addEventListener('input', (e) => {
        this.filters.contextId = (e.target as HTMLInputElement).value;
        this.currentPage = 0;
        this.loadTasks();
      });

      document.getElementById('refresh-tasks-btn')?.addEventListener('click', () => {
        this.loadTasks();
      });

      // Pagination
      document.getElementById('prev-page-btn')?.addEventListener('click', () => {
        if (this.currentPage > 0) {
          this.currentPage--;
          this.loadTasks();
        }
      });

      document.getElementById('next-page-btn')?.addEventListener('click', () => {
        this.currentPage++;
        this.loadTasks();
      });

      // Task detail modal close
      document.getElementById('task-detail-close')?.addEventListener('click', () => {
        document.getElementById('task-detail-modal')?.classList.add('hidden');
      });
    }

    private setupSocketListeners() {
      // Listen for task updates
      socket.on('task_update', (data: {task: Task}) => {
        console.log('Task update received:', data);
        this.updateTask(data.task);
      });

      // Listen for task subscription responses
      socket.on('task_subscription_response', (data: {status: string; tasks?: Task[]; total?: number}) => {
        console.log('Task subscription response:', data);
        if (data.status === 'success' && data.tasks) {
          data.tasks.forEach((task) => this.updateTask(task));
          this.renderTaskList();
          this.loadStats();
        }
      });
    }

    setAgentUrl(url: string) {
      this.currentAgentUrl = url;
      // Subscribe to task updates for this agent
      socket.emit('subscribe_to_tasks', {agent_url: url});
    }

    private updateTask(task: Task) {
      this.tasks.set(task.id, task);
      // Re-render if we're on the tasks tab
      const tasksView = document.getElementById('tasks-view');
      if (tasksView && !tasksView.classList.contains('hidden')) {
        this.renderTaskList();
        this.loadStats();
      }
    }

    async loadTasks() {
      if (!this.currentAgentUrl) {
        console.warn('No agent URL set');
        return;
      }

      try {
        const params = new URLSearchParams({
          agent_url: this.currentAgentUrl,
          limit: this.limit.toString(),
          offset: (this.currentPage * this.limit).toString(),
        });

        if (this.filters.state) {
          params.append('state', this.filters.state);
        }
        if (this.filters.contextId) {
          params.append('context_id', this.filters.contextId);
        }

        const response = await fetch(`/api/tasks?${params}`);
        const data = await response.json();

        // Update local cache
        data.tasks.forEach((task: Task) => {
          this.tasks.set(task.id, task);
        });

        this.renderTaskList();
        this.updatePagination(data.total);
        await this.loadStats();
      } catch (error) {
        console.error('Failed to load tasks:', error);
      }
    }

    private async loadStats() {
      if (!this.currentAgentUrl) return;

      try {
        const response = await fetch(`/api/tasks/stats?agent_url=${encodeURIComponent(this.currentAgentUrl)}`);
        const stats: TaskStats = await response.json();
        this.renderStats(stats);
      } catch (error) {
        console.error('Failed to load stats:', error);
      }
    }

    private renderStats(stats: TaskStats) {
      document.getElementById('stat-total')!.textContent = stats.total.toString();
      document.getElementById('stat-active')!.textContent = stats.active.toString();
      document.getElementById('stat-completed')!.textContent = stats.completed.toString();
      document.getElementById('stat-failed')!.textContent = stats.failed.toString();
    }

    private renderTaskList() {
      const taskList = document.getElementById('task-list')!;

      // Get filtered tasks
      let filteredTasks = Array.from(this.tasks.values());

      if (this.filters.state) {
        filteredTasks = filteredTasks.filter((t) => t.status.state === this.filters.state);
      }
      if (this.filters.contextId) {
        filteredTasks = filteredTasks.filter((t) => t.contextId?.includes(this.filters.contextId));
      }

      // Sort by status timestamp descending
      filteredTasks.sort((a, b) => {
        const dateA = a.status.timestamp ? new Date(a.status.timestamp).getTime() : 0;
        const dateB = b.status.timestamp ? new Date(b.status.timestamp).getTime() : 0;
        return dateB - dateA;
      });

      if (filteredTasks.length === 0) {
        taskList.innerHTML = '<p class="placeholder-text">No tasks found</p>';
        return;
      }

      // Create table
      const table = document.createElement('table');
      table.className = 'task-table';

      // Create table header
      const thead = document.createElement('thead');
      thead.innerHTML = `
        <tr>
          <th>Task ID</th>
          <th>State</th>
          <th>Context ID</th>
          <th>Updated</th>
        </tr>
      `;
      table.appendChild(thead);

      // Create table body
      const tbody = document.createElement('tbody');
      filteredTasks.forEach((task) => {
        const row = this.createTaskRow(task);
        tbody.appendChild(row);
      });
      table.appendChild(tbody);

      taskList.innerHTML = '';
      taskList.appendChild(table);
    }

    private createTaskRow(task: Task): HTMLElement {
      const row = document.createElement('tr');
      row.dataset.taskId = task.id;
      row.style.cursor = 'pointer';

      // Task ID column
      const idCell = document.createElement('td');
      idCell.className = 'task-id';
      idCell.textContent = this.truncateId(task.id);
      idCell.title = task.id; // Show full ID on hover
      row.appendChild(idCell);

      // Status column
      const statusCell = document.createElement('td');
      const statusBadge = document.createElement('span');
      statusBadge.className = `task-status-badge ${task.status.state}`;
      statusBadge.textContent = task.status.state;
      statusCell.appendChild(statusBadge);
      row.appendChild(statusCell);

      // Context ID column
      const contextCell = document.createElement('td');
      contextCell.className = 'context-id';
      contextCell.textContent = task.contextId ? this.truncateId(task.contextId) : '-';
      contextCell.title = task.contextId || ''; // Show full context ID on hover
      row.appendChild(contextCell);

      // Updated column
      const timeCell = document.createElement('td');
      timeCell.className = 'task-time';
      timeCell.textContent = task.status.timestamp ? this.formatRelativeTime(task.status.timestamp) : '-';
      row.appendChild(timeCell);

      // Click handler to show details
      row.addEventListener('click', () => {
        this.showTaskDetail(task);
      });

      return row;
    }

    private truncateId(id: string): string {
      return id.substring(0, 12) + '...';
    }

    private formatRelativeTime(timestamp: string): string {
      const now = new Date();
      const then = new Date(timestamp);
      const diff = now.getTime() - then.getTime();
      const seconds = Math.floor(diff / 1000);
      const minutes = Math.floor(seconds / 60);
      const hours = Math.floor(minutes / 60);
      const days = Math.floor(hours / 24);

      if (seconds < 60) return 'Just now';
      if (minutes < 60) return `${minutes} min${minutes > 1 ? 's' : ''} ago`;
      if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
      if (days < 7) return `${days} day${days > 1 ? 's' : ''} ago`;
      return then.toLocaleDateString();
    }

    private showTaskDetail(task: Task) {
      const modal = document.getElementById('task-detail-modal')!;

      // Populate overview
      document.getElementById('detail-task-id')!.textContent = task.id;
      document.getElementById('detail-context-id')!.textContent = task.contextId || 'N/A';

      const statusBadge = document.getElementById('detail-status')!;
      statusBadge.textContent = task.status.state;
      statusBadge.className = `task-status-badge ${task.status.state}`;

      document.getElementById('detail-created')!.textContent = task.status.timestamp ? this.formatDate(task.status.timestamp) : 'N/A';
      document.getElementById('detail-updated')!.textContent = task.status.timestamp ? this.formatDate(task.status.timestamp) : 'N/A';

      // Populate history
      const historyDiv = document.getElementById('detail-history')!;
      if (task.history && task.history.length > 0) {
        historyDiv.innerHTML = '';
        task.history.forEach((msg) => {
          const historyItem = document.createElement('div');
          historyItem.className = 'history-item';

          const role = document.createElement('div');
          role.className = 'history-item-role';
          role.textContent = msg.role;

          const content = document.createElement('div');
          content.className = 'history-item-content';
          const text = msg.parts?.map((p) => p.text).join('\n') || '';
          content.textContent = text;

          historyItem.appendChild(role);
          historyItem.appendChild(content);
          historyDiv.appendChild(historyItem);
        });
      } else {
        historyDiv.innerHTML = '<p class="placeholder-text">No history</p>';
      }

      // Populate artifacts
      const artifactsDiv = document.getElementById('detail-artifacts')!;
      if (task.artifacts && task.artifacts.length > 0) {
        artifactsDiv.innerHTML = '';
        task.artifacts.forEach((artifact) => {
          const artifactItem = document.createElement('div');
          artifactItem.className = 'artifact-item';

          if (artifact.name) {
            const name = document.createElement('div');
            name.className = 'artifact-item-name';
            name.textContent = artifact.name;
            artifactItem.appendChild(name);
          }

          if (artifact.description) {
            const desc = document.createElement('div');
            desc.className = 'artifact-item-description';
            desc.textContent = artifact.description;
            artifactItem.appendChild(desc);
          }

          if (artifact.parts) {
            const contentDiv = document.createElement('div');
            contentDiv.className = 'artifact-item-content';
            const text = artifact.parts.map((p) => 'text' in p ? p.text : JSON.stringify(p, null, 2)).join('\n');
            contentDiv.textContent = text;
            artifactItem.appendChild(contentDiv);
          }

          artifactsDiv.appendChild(artifactItem);
        });
      } else {
        artifactsDiv.innerHTML = '<p class="placeholder-text">No artifacts</p>';
      }

      // Setup action buttons
      const rawJsonBtn = document.getElementById('task-detail-raw-json')!;
      rawJsonBtn.onclick = () => {
        showJsonInModal(task);
      };

      const cancelBtn = document.getElementById('task-detail-cancel')!;
      if (task.status.state === 'submitted' || task.status.state === 'working') {
        cancelBtn.classList.remove('hidden');
        cancelBtn.onclick = () => {
          this.cancelTask(task.id);
        };
      } else {
        cancelBtn.classList.add('hidden');
      }

      modal.classList.remove('hidden');
    }

    private async cancelTask(taskId: string) {
      if (!this.currentAgentUrl) return;

      try {
        socket.emit('cancel_task', {
          task_id: taskId,
          agent_url: this.currentAgentUrl,
        });

        // Close the modal
        document.getElementById('task-detail-modal')?.classList.add('hidden');
      } catch (error) {
        console.error('Failed to cancel task:', error);
      }
    }

    private updatePagination(total: number) {
      const paginationDiv = document.getElementById('task-pagination')!;
      const prevBtn = document.getElementById('prev-page-btn') as HTMLButtonElement;
      const nextBtn = document.getElementById('next-page-btn') as HTMLButtonElement;
      const pageInfo = document.getElementById('page-info')!;

      const totalPages = Math.ceil(total / this.limit);

      if (totalPages > 1) {
        paginationDiv.classList.remove('hidden');
        prevBtn.disabled = this.currentPage === 0;
        nextBtn.disabled = this.currentPage >= totalPages - 1;
        pageInfo.textContent = `Page ${this.currentPage + 1} of ${totalPages}`;
      } else {
        paginationDiv.classList.add('hidden');
      }
    }

    private formatDate(dateString: string): string {
      const date = new Date(dateString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);

      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins} min ago`;
      if (diffHours < 24) return `${diffHours} hr ago`;
      if (diffDays < 7) return `${diffDays} days ago`;

      return date.toLocaleDateString();
    }
  }

  // Initialize task dashboard
  const taskDashboard = new TaskDashboard();

  // Update task dashboard when agent is connected
  const originalClientInitializedHandler = () => {
    // Get agent URL from card input and trim whitespace
    const agentUrl = (document.getElementById('agent-card-url') as HTMLInputElement).value.trim();
    if (agentUrl) {
      taskDashboard.setAgentUrl(agentUrl);
    }
  };

  socket.on('client_initialized', (data) => {
    if (data.status === 'success') {
      originalClientInitializedHandler();
    }
  });
});
