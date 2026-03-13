<script>
  import { onMount, afterUpdate } from "svelte";
  import "./app.css";

  let stats = {
    total: 0,
    pending: 0,
    downloading: 0,
    completed: 0,
    failed: 0,
    free_space_gb: 0,
    ip: "Unknown",
  };

  let fastMode = false;
  let isToggling = false;

  let events = [];
  let socket;
  let eventContainer;
  let connectionStatus = "CONNECTING...";
  let pingIntervalId;

  let activeTab = "CRAWLER";
  let scansStats = null;
  let vulnerableScans = [];
  let expandedScans = {};
  let allExpanded = false;
  let hideAppNames = false;

  function addEvent(event) {
    if (event.type === "init_stats") {
      stats = event.data;
      return; // DON'T show stats updates in the log feed
    }

    events = [
      ...events,
      {
        ...event,
        id: Date.now(),
        timestamp: event.timestamp || Date.now() / 1000,
      },
    ];
    if (events.length > 200) events = events.slice(1);
  }

  function scrollToBottom() {
    if (eventContainer) {
      eventContainer.scrollTop = eventContainer.scrollHeight;
    }
  }

  function connect() {
    connectionStatus = "CONNECTING...";
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.hostname}:8000/ws`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      connectionStatus = "ONLINE";
      addEvent({
        type: "sys",
        level: "success",
        message: "CONNECTION_ESTABLISHED",
      });

      // Ping
      pingIntervalId = setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send("ping");
        }
      }, 15000);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        addEvent(data);
      } catch (e) {
        console.error("Failed to parse event:", e);
      }
    };

    socket.onclose = () => {
      connectionStatus = "OFFLINE";
      if (pingIntervalId) clearInterval(pingIntervalId);
      addEvent({
        type: "sys",
        level: "error",
        message: "CONNECTION_LOST_RETRYING...",
      });
      setTimeout(connect, 3000);
    };

    socket.onerror = () => {
      connectionStatus = "ERROR";
    };
  }

  async function fetchSettings() {
    try {
      const res = await fetch(`http://${window.location.hostname}:8000/settings`);
      const data = await res.json();
      fastMode = !!data.fast_mode;
    } catch (e) {
      console.error("Failed to fetch settings:", e);
    }
  }

  async function fetchScansData() {
    try {
      const resStats = await fetch(`http://${window.location.hostname}:8000/scans/stats`);
      scansStats = await resStats.json();
      
      const resVuln = await fetch(`http://${window.location.hostname}:8000/scans/vulnerable`);
      vulnerableScans = await resVuln.json();
    } catch (e) {
      console.error("Failed to fetch scans data:", e);
    }
  }

  async function toggleFastMode() {
    if (isToggling) return;
    isToggling = true;
    const newState = !fastMode;
    try {
      const res = await fetch(`http://${window.location.hostname}:8000/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fast_mode: newState }),
      });
      if (res.ok) {
        fastMode = newState;
      }
    } catch (e) {
      console.error("Failed to toggle settings:", e);
    } finally {
      isToggling = false;
    }
  }

  function toggleExpandAll() {
    allExpanded = !allExpanded;
    if (allExpanded) {
        vulnerableScans.forEach(scan => {
            expandedScans[scan._id] = true;
        });
    } else {
        expandedScans = {};
    }
  }

  function toggleExpand(id) {
      expandedScans[id] = !expandedScans[id];
      expandedScans = {...expandedScans}; // trigger reactivity
  }

  function toggleHideNames() {
      hideAppNames = !hideAppNames;
  }

  onMount(() => {
    connect();
    fetchSettings();
    fetchScansData();
    setInterval(fetchScansData, 10000); // refresh every 10s
  });

  afterUpdate(() => {
    scrollToBottom();
  });

  function getLevelColor(level) {
    switch (level) {
      case "warning":
        return "text-yellow-500";
      case "error":
        return "text-red-500 font-bold";
      case "success":
        return "text-[#00FF41] shadow-[0_0_8px_rgba(0,255,65,0.6)]";
      default:
        return "text-[#00FF41] opacity-90";
    }
  }

  function formatTime(ts) {
    if (!ts) return "--:--:--";
    const d = new Date(ts * 1000);
    return d.toTimeString().split(" ")[0];
  }
</script>

<main
  class="min-h-screen bg-black text-[#00FF41] font-mono p-8 md:p-16 relative overflow-hidden flex flex-col items-center"
>
  <!-- Scanline Effect Overlay -->
  <div
    class="pointer-events-none fixed inset-0 z-50 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_3px,3px_100%] opacity-20"
  ></div>

  <div class="w-full max-w-7xl relative z-10 transition-all duration-500">
    <!-- Header -->
    <header
      class="border-2 border-[#00FF41]/30 p-8 md:p-12 mb-12 flex flex-col lg:flex-row justify-between items-start lg:items-center gap-8 bg-[#00FF41]/5 backdrop-blur-md shadow-[0_0_30px_rgba(0,59,0,0.3)] rounded-lg"
    >
      <div class="space-y-4">
        <h1
          class="text-4xl md:text-6xl font-black tracking-[0.25em] uppercase text-[#00FF41] drop-shadow-[0_0_15px_rgba(0,255,65,0.6)]"
        >
          SCRAPER.v2.1
        </h1>
        <p
          class="text-[10px] md:text-sm tracking-widest flex items-center gap-3"
        >
          <span
            class="inline-block w-2 h-2 rounded-full {connectionStatus ===
            'ONLINE'
              ? 'bg-[#00FF41] shadow-[0_0_8px_#00ff41]'
              : 'bg-red-500 animate-pulse'}"
          ></span>
          <span class="opacity-60">SYSTEM_NODE:</span>
          <span class="text-[#00FF41] font-bold">READY</span>
          <span class="opacity-60">//</span>
          <span class="opacity-60">SOCKET_PIPE:</span>
          <span
            class={connectionStatus === "ONLINE"
              ? "text-[#00FF41] font-bold uppercase"
              : "text-red-500 animate-pulse lowercase"}>{connectionStatus}</span
          >
        </p>
      </div>

      <div
        class="flex flex-col lg:items-end gap-3 text-xs tracking-widest uppercase border-l-4 border-[#00FF41]/20 pl-6 lg:pl-0 lg:border-l-0 lg:pr-8"
      >
        <button
          class="mb-2 relative overflow-hidden group border-2 border-[#00FF41]/40 px-4 py-2 font-bold tracking-widest transition-all duration-300 w-full lg:w-48 {fastMode ? 'bg-[#00FF41]/20 text-white border-[#00FF41] shadow-[0_0_15px_rgba(0,255,65,0.4)]' : 'hover:bg-[#00FF41]/10 text-gray-400 opacity-60'}"
          on:click={toggleFastMode}
          disabled={isToggling}
        >
          <div class="absolute inset-0 w-full h-full bg-[#00FF41]/10 transform -translate-x-full group-hover:translate-x-0 transition-transform duration-300"></div>
          <span class="relative z-10 flex items-center justify-center gap-2">
            {#if fastMode}
              <span class="text-red-500 animate-pulse">⚡</span> FAST MODE: ON
            {:else}
              FAST MODE: OFF
            {/if}
          </span>
        </button>

        <div
          class="flex justify-between lg:justify-end items-center gap-6 w-full lg:w-auto"
        >
          <span class="opacity-40">PUB_ADDR:</span>
          <span
            class="text-[#00FF41] font-bold text-sm bg-[#00FF41]/10 px-2 py-0.5 rounded border border-[#00FF41]/20"
            >{stats.ip}</span
          >
        </div>
        <div
          class="flex justify-between lg:justify-end items-center gap-6 w-full lg:w-auto"
        >
          <span class="opacity-40">STORE_VOL:</span>
          <span class="text-[#00FF41] font-bold">/apps/</span>
        </div>
        <div
          class="flex justify-between lg:justify-end items-center gap-6 w-full lg:w-auto"
        >
          <span class="opacity-40">FREE_DISK:</span>
          <span class="text-[#00FF41] font-bold text-sm tracking-normal"
            >{stats.free_space_gb} GB</span
          >
        </div>
      </div>
    </header>

    <!-- Tab Navigation -->
    <div class="flex gap-4 mb-8 border-b border-[#00FF41]/30 pb-4">
      <button 
        class="px-6 py-2 font-bold tracking-widest transition-all {activeTab === 'CRAWLER' ? 'bg-[#00FF41]/20 text-white border-b-2 border-[#00FF41]' : 'text-gray-500 hover:text-[#00FF41]/70'}"
        on:click={() => activeTab = 'CRAWLER'}
      >
        CRAWLER FEED
      </button>
      <button 
        class="px-6 py-2 font-bold tracking-widest transition-all flex items-center gap-2 {activeTab === 'SCANS' ? 'bg-[#00FF41]/20 text-white border-b-2 border-[#00FF41]' : 'text-gray-500 hover:text-[#00FF41]/70'}"
        on:click={() => {activeTab = 'SCANS'; fetchScansData();}}
      >
        SCAN RESULTS
        {#if scansStats && scansStats.vulnerable_apps > 0}
            <span class="bg-red-500 text-black text-[10px] px-2 py-0.5 rounded-full animate-pulse flex-shrink-0">{scansStats.vulnerable_apps}</span>
        {/if}
      </button>
    </div>

    {#if activeTab === 'CRAWLER'}
    <!-- Stats Grid -->
    <section class="grid grid-cols-3 lg:grid-cols-5 gap-4 mb-12">
      {#each [{ label: "DISCOVERED", key: "total", color: "border-[#00FF41]/20", sub: "entries" }, { label: "PENDING", key: "pending", color: "border-[#00FF41]/20 text-blue-400", sub: "waiting" }, { label: "ACTIVE", key: "downloading", color: "border-[#00FF41]/40 shadow-[0_0_20px_rgba(0,255,65,0.1)]", sub: "workers" }, { label: "COMPLETED", key: "completed", color: "border-[#00FF41] border-2 shadow-[0_0_25px_rgba(0,255,65,0.3)]", sub: "succ_dl" }, { label: "FAILED", key: "failed", color: "border-red-900/50 text-red-500", sub: "aborted" }] as stat}
        <div
          class="border p-6 md:p-8 bg-black/60 flex flex-col justify-between transition-all hover:bg-[#00FF41]/10 hover:shadow-[0_0_25px_rgba(0,255,65,0.1)] rounded-md border-opacity-40 {stat.color}"
        >
          <span
            class="text-[10px] md:text-xs uppercase tracking-[0.4em] opacity-30"
            >{stat.label}</span
          >
          <div class="flex items-baseline gap-2">
            <span class="text-4xl md:text-5xl font-black tracking-tighter">
              {stats[stat.key]}
            </span>
            <span class="text-[8px] opacity-20 uppercase tracking-widest"
              >{stat.sub}</span
            >
          </div>
        </div>
      {/each}
    </section>

    <!-- Live Events Feed -->
    <section
      class="border-2 border-[#00FF41]/30 bg-black/90 shadow-2xl relative rounded-lg"
    >
      <div
        class="bg-[#00FF41]/20 px-8 py-4 text-xs font-bold border-b border-[#00FF41]/30 flex justify-between items-center tracking-[0.2em] relative overflow-hidden group rounded-t-lg"
      >
        <span class="z-10 text-[#00FF41]">__SIGNAL_STREAM.LOG</span>
        <div class="flex items-center gap-6 z-10">
          <span class="opacity-60">BUF_SIZE: {events.length}</span>
          <span class="text-red-500 animate-[pulse_1s_infinite]">● REC</span>
        </div>
        <!-- Progress bar line -->
        <div
          class="absolute bottom-0 left-0 h-[3px] bg-[#00FF41] w-full animate-[shimmer_2s_infinite]"
        ></div>
      </div>

      <div
        bind:this={eventContainer}
        class="h-[500px] overflow-y-auto p-10 space-y-3 text-xs md:text-sm custom-scrollbar bg-[radial-gradient(circle_at_center,rgba(0,59,0,0.05)_0%,transparent_100%)] rounded-b-lg"
      >
        {#each events as event (event.id)}
          <div
            class="flex flex-col md:flex-row md:items-start gap-2 md:gap-6 group hover:bg-[#00FF41]/5 p-2 -m-2 rounded transition-colors"
          >
            <span
              class="opacity-30 text-[11px] w-24 flex-shrink-0 select-none hidden md:block mt-0.5"
            >
              [{formatTime(event.timestamp)}]
            </span>
            <span
              class="opacity-50 font-bold uppercase text-[10px] tracking-[0.3em] w-28 flex-shrink-0 border border-[#00FF41]/20 px-2 py-0.5 text-center select-none rounded bg-black/50"
            >
              {event.type}
            </span>
            <span
              class="{getLevelColor(
                event.level,
              )} flex-grow leading-relaxed break-all font-bold"
            >
              {event.message}
              {#if event.data && Object.keys(event.data).length > 0}
                <details class="block mt-2">
                  <summary
                    class="cursor-pointer opacity-40 hover:opacity-100 text-[10px] select-none tracking-[0.2em] uppercase transition-opacity outline-none"
                    >>> [ EXPAND_DATA_PAYLOAD ]</summary
                  >
                  <pre
                    class="bg-[#00FF41]/5 p-4 mt-3 rounded border border-[#00FF41]/20 text-[11px] overflow-x-auto text-[#00FF41]/70 shadow-inner">
{JSON.stringify(event.data, null, 2)}
                  </pre>
                </details>
              {/if}
            </span>
          </div>
        {/each}

        {#if events.length === 0}
          <div
            class="flex items-center gap-4 opacity-40 animate-pulse py-4 font-bold tracking-[0.2em]"
          >
            <span class="loading-cursor scale-150 inline-block">_</span>
            <span>WAITING FOR INBOUND DATA STREAM...</span>
          </div>
        {/if}
      </div>
    </section>
    {:else if activeTab === 'SCANS'}
        {#if scansStats}
        <section class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-12">
            <div class="border border-[#00FF41]/30 p-6 bg-black/60 flex flex-col justify-between">
                <span class="text-[10px] uppercase tracking-[0.2em] opacity-40">APPS SCANNED</span>
                <span class="text-3xl font-black">{scansStats.total_apps_scanned}</span>
            </div>
            <div class="border border-[#00FF41]/30 p-6 bg-black/60 flex flex-col justify-between">
                <span class="text-[10px] uppercase tracking-[0.2em] opacity-40">APPS WITH KEYS</span>
                <div class="flex items-baseline gap-2">
                    <span class="text-3xl font-black">{scansStats.apps_with_keys}</span>
                    <span class="text-xs opacity-50">({scansStats.percent_apps_with_keys}%)</span>
                </div>
            </div>
            <div class="border border-[#00FF41]/30 p-6 bg-black/60 flex flex-col justify-between relative overflow-hidden">
                <div class="absolute inset-0 bg-red-500/5"></div>
                <span class="text-[10px] uppercase tracking-[0.2em] text-red-400 relative z-10">VULNERABLE APPS</span>
                <div class="flex items-baseline gap-2 relative z-10">
                    <span class="text-3xl font-black text-red-500 drop-shadow-[0_0_8px_rgba(255,0,0,0.5)]">{scansStats.vulnerable_apps}</span>
                    <span class="text-xs text-red-500/50">({scansStats.percent_vulnerable_apps}%)</span>
                </div>
            </div>
            <div class="border border-[#00FF41]/30 p-6 bg-black/60 flex flex-col justify-between">
                <span class="text-[10px] uppercase tracking-[0.2em] opacity-40">VULNERABLE ENDPOINTS</span>
                <div class="flex items-baseline gap-2">
                    <span class="text-3xl font-black text-yellow-500">{scansStats.total_working_endpoints}</span>
                    <span class="text-[8px] opacity-40 uppercase">EXPOSED APIs</span>
                </div>
            </div>
        </section>
        {/if}

        <section class="border-2 border-[#00FF41]/30 bg-black/90 shadow-2xl rounded-lg overflow-hidden">
            <div class="bg-[#00FF41]/20 px-8 py-4 text-xs font-bold border-b border-[#00FF41]/30 tracking-[0.2em] flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <span class="text-[#00FF41]">__VULNERABLE_PACKAGE_INDEX</span>
                {#if vulnerableScans.length > 0}
                    <div class="flex gap-4">
                        <button class="hover:text-white transition-colors border border-[#00FF41]/40 px-3 py-1 bg-black/50 rounded flex items-center gap-2" on:click={toggleHideNames}>
                            <span class="w-2 h-2 rounded-full {hideAppNames ? 'bg-red-500 shadow-[0_0_5px_#ef4444]' : 'bg-[#00FF41] shadow-[0_0_5px_#00ff41]'}"></span>
                            {hideAppNames ? 'SHOW_NAMES' : 'CENSOR_NAMES'}
                        </button>
                        <button class="hover:text-white transition-colors border border-[#00FF41]/40 px-3 py-1 bg-black/50 rounded" on:click={toggleExpandAll}>
                            {allExpanded ? 'COLLAPSE_ALL' : 'EXPAND_ALL'}
                        </button>
                    </div>
                {/if}
            </div>
            <div class="p-8 space-y-4 max-h-[600px] overflow-y-auto custom-scrollbar">
                {#if vulnerableScans.length === 0}
                    <div class="opacity-50 tracking-[0.2em] text-center py-12">NO VULNERABILITIES DETECTED RECORD.</div>
                {:else}
                    {#each vulnerableScans as scan}
                        {#each scan.results as result (result.key)}
                            {#if result.working_count > 0}
                                <div class="border border-[#00FF41]/20 bg-black/50 p-6 flex flex-col gap-4 group hover:border-[#00FF41]/50 transition-colors cursor-pointer" on:click={() => toggleExpand(scan._id)}>
                                    <div class="flex justify-between items-start">
                                        <div class="flex flex-col">
                                            <span class="text-xs opacity-50 tracking-widest">{formatTime(scan.at)}</span>
                                            <span class="text-lg font-bold tracking-wider relative overflow-hidden group-hover:text-white transition-colors">
                                                {hideAppNames ? scan.filename.replace(/^(.{3}).*$/, '$1***.apk') : scan.filename}
                                            </span>
                                        </div>
                                        <div class="flex flex-col items-end gap-2">
                                            <span class="text-[10px] font-mono opacity-40 px-3 py-1 bg-white/5 rounded border border-white/10">{result.key.replace(/^(.{6}).*(.{6})$/, '$1***$2')}</span>
                                            <span class="text-[10px] tracking-widest text-[#00FF41]/60 group-hover:text-[#00FF41]">{expandedScans[scan._id] ? '[-]' : '[+]'}</span>
                                        </div>
                                    </div>

                                    {#if !expandedScans[scan._id]}
                                    <!-- Minimized View -->
                                    <div class="flex flex-wrap gap-2 mt-2">
                                        {#each result.working as api}
                                            <span class="text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30 px-3 py-1 rounded shadow-[0_0_5px_rgba(255,0,0,0.2)]">
                                                {api}
                                            </span>
                                        {/each}
                                    </div>
                                    {:else}
                                    <!-- Expanded Matrix View -->
                                    <div class="mt-4 border-t border-[#00FF41]/20 pt-4 cursor-default" on:click|stopPropagation>
                                        <div class="font-mono text-xs space-y-2 bg-[#00FF41]/5 p-4 rounded border border-[#00FF41]/10">
                                            {#each result.results as test}
                                                <div class="flex items-center gap-4">
                                                    <span class="w-32 opacity-70 {test[1] === 'WORKING' ? 'text-red-400 font-bold' : ''}">{test[0]}</span>
                                                    <span class="w-8 opacity-40">→</span>
                                                    <span class="w-24 font-bold {test[1] === 'WORKING' ? 'text-red-500' : 'text-gray-500'}">
                                                        {test[1]}
                                                    </span>
                                                    <span class="opacity-60 truncate {test[1] === 'WORKING' ? 'text-red-300' : ''}">{test[2]}</span>
                                                </div>
                                            {/each}
                                            <div class="mt-4 pt-2 border-t border-[#00FF41]/10 flex justify-between items-center text-[#00FF41]/80 font-bold tracking-widest">
                                                <span>→ {result.working_count}/{result.results.length} ENDPOINTS COMPROMISED</span>
                                                <span class="text-red-500 animate-pulse">! DATA_EXFILTRATION_POSSIBLE !</span>
                                            </div>
                                        </div>
                                    </div>
                                    {/if}
                                </div>
                            {/if}
                        {/each}
                    {/each}
                {/if}
            </div>
        </section>
    {/if}

    <!-- Footer -->
    <footer
      class="mt-12 pt-8 border-t border-[#00FF41]/20 text-[10px] md:text-xs text-[#00FF41]/40 flex flex-col md:flex-row justify-between items-center gap-6 uppercase tracking-[0.3em] font-bold pb-12"
    >
      <div class="flex gap-8">
        <span>&copy; DISTRIBUTED_SCRAPER</span>
        <span class="hidden md:inline text-gray-500 transition-colors duration-300 {fastMode ? 'text-red-500' : ''}"
          >SECURITY: <span class={fastMode ? 'text-red-600 animate-pulse' : 'text-[#00FF41]/70'}>
            {fastMode ? 'BYPASS_WARNING (FAST MODE)' : 'BYPASS_ACTIVE'}
          </span>
        </span>
      </div>
      <div class="animate-[pulse_3s_infinite] flex items-center gap-2">
        <span class="text-[#00FF41]">></span> TERMINAL_READY ._
      </div>
    </footer>
  </div>
</main>

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    background-color: black;
    overflow-x: hidden;
  }

  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.8);
    border-radius: 4px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(0, 255, 65, 0.2);
    border-radius: 4px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 255, 65, 0.5);
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.3;
    }
  }

  @keyframes shimmer {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(100%);
    }
  }

  .loading-cursor {
    animation: blink 1s step-end infinite;
  }

  @keyframes blink {
    from,
    to {
      opacity: 1;
    }
    50% {
      opacity: 0;
    }
  }
</style>
