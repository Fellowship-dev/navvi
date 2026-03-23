#!/usr/bin/env node
/**
 * Navvi CLI + MCP entry point.
 *
 * No args / piped stdin  → run as MCP stdio server (for Claude Code)
 * Subcommand             → CLI mode (build, start, stop, status, vnc)
 */

import { execSync } from 'child_process';
import { createRequire } from 'module';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PACKAGE_DIR = path.resolve(__dirname, '..');
const cmd = process.argv[2];

// --- MCP mode: no args and stdin is not a TTY (piped by MCP client) ---
if (!cmd && !process.stdin.isTTY) {
  const serverPath = path.join(PACKAGE_DIR, 'mcp', 'server.mjs');
  process.env.NAVVI_PACKAGE_DIR = PACKAGE_DIR;
  await import(serverPath);
  // server.mjs sets up stdin/stdout listeners and runs forever
}

// --- CLI mode ---
else {
  const IMAGE = process.env.NAVVI_IMAGE || 'navvi';
  const PREFIX = 'navvi-';

  function sh(command) {
    try {
      return execSync(command, { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }).trim();
    } catch (e) {
      return e.stderr ? e.stderr.trim() : e.message;
    }
  }

  function version() {
    try {
      const pkg = JSON.parse(fs.readFileSync(path.join(PACKAGE_DIR, 'package.json'), 'utf8'));
      return pkg.version;
    } catch {
      return 'unknown';
    }
  }

  switch (cmd) {
    case 'build': {
      const dockerfile = path.join(PACKAGE_DIR, 'container');
      console.log(`Building Navvi Docker image from ${dockerfile}...`);
      try {
        execSync(`docker build -t ${IMAGE} ${dockerfile}`, { stdio: 'inherit' });
        console.log(`\nDone. Image: ${IMAGE}`);
      } catch {
        process.exit(1);
      }
      break;
    }

    case 'start': {
      const persona = process.argv[3] || 'default';
      const cname = `${PREFIX}${persona}`;
      const existing = sh(`docker ps -q --filter "name=${cname}" 2>/dev/null`);
      if (existing) {
        console.log(`Already running: ${cname}`);
        break;
      }
      sh(`docker rm ${cname} 2>/dev/null`);
      const volume = `navvi-profile-${persona}`;
      console.log(`Starting ${persona}...`);
      const result = sh(`docker run -d --name ${cname} -p 8024:8024 -p 6080:6080 -v ${volume}:/home/user/.mozilla ${IMAGE}`);
      if (result.includes('Error')) {
        console.error(result);
        console.error(`\nIs the image built? Run: navvi build`);
        process.exit(1);
      }
      console.log(`Container: ${cname}`);
      console.log(`API:       http://127.0.0.1:8024`);
      console.log(`VNC:       http://127.0.0.1:6080/vnc.html?autoconnect=true`);
      console.log(`Volume:    ${volume}`);
      break;
    }

    case 'stop': {
      const persona = process.argv[3];
      if (persona) {
        sh(`docker stop ${PREFIX}${persona} 2>/dev/null`);
        sh(`docker rm ${PREFIX}${persona} 2>/dev/null`);
        console.log(`Stopped: ${PREFIX}${persona}`);
      } else {
        const containers = sh(`docker ps --filter "name=${PREFIX}" --format "{{.Names}}" 2>/dev/null`);
        if (!containers) { console.log('No running Navvi containers.'); break; }
        for (const c of containers.split('\n')) {
          sh(`docker stop ${c} 2>/dev/null`);
          sh(`docker rm ${c} 2>/dev/null`);
          console.log(`Stopped: ${c}`);
        }
      }
      break;
    }

    case 'status': {
      const containers = sh(`docker ps --filter "name=${PREFIX}" --format "{{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null`);
      if (!containers) { console.log('No running Navvi containers.'); break; }
      console.log('Running:');
      for (const line of containers.split('\n')) {
        const [name, status, ports] = line.split('\t');
        console.log(`  ${name.replace(PREFIX, '')} — ${status}`);
      }
      break;
    }

    case 'vnc': {
      const persona = process.argv[3] || 'default';
      console.log(`http://127.0.0.1:6080/vnc.html?autoconnect=true`);
      break;
    }

    case '--version':
    case '-v':
      console.log(`navvi ${version()}`);
      break;

    case '--help':
    case '-h':
    case 'help':
    case undefined:
      console.log(`navvi ${version()} — Give your AI agent a real browser identity.

Usage:
  navvi                   Run as MCP server (for Claude Code)
  navvi build             Build the Docker image (one-time setup)
  navvi start [persona]   Start a browser container
  navvi stop [persona]    Stop container(s)
  navvi status            List running containers
  navvi vnc [persona]     Show noVNC URL for live view
  navvi --version         Show version

MCP setup:
  Add to .mcp.json:  { "mcpServers": { "navvi": { "command": "navvi" } } }
  Or use npx:        { "command": "npx", "args": ["-y", "navvi"] }`);
      break;

    default:
      console.error(`Unknown command: ${cmd}\nRun: navvi --help`);
      process.exit(1);
  }
}
