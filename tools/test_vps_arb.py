"""Test ARB scanner on VPS."""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.143.138.8', username='root', password='p4RCcQUr')

# Test ARB scanner
cmd = """
cd /root/polymarket-bot
source venv/bin/activate
python -c '
import asyncio
import logging
logging.basicConfig(level=logging.INFO)

async def test():
    from src.scanner.arb_scanner import ARBScanner
    async with ARBScanner(min_roi_pct=2.5) as scanner:
        print("ARBScanner initialized:", scanner.get_stats())

asyncio.run(test())
'
"""

stdin, stdout, stderr = ssh.exec_command(cmd)
print('STDOUT:', stdout.read().decode())
print('STDERR:', stderr.read().decode())

ssh.close()
