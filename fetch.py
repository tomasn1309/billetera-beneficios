"""Descarga las páginas de beneficios con un navegador real (Playwright),
porque los sitios de los bancos arman el contenido con JavaScript."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")


@dataclass
class Page:
    url: str
    ok: bool
    text: str = ""
    links: list[str] = field(default_factory=list)
    error: str | None = None


async def _grab(ctx, url: str, timeout_ms: int = 45000) -> Page:
    page = await ctx.new_page()
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if resp is not None and resp.status >= 400:
            return Page(url, False, error=f"HTTP {resp.status}")
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        for _ in range(6):  # gatilla carga diferida
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(600)
        for label in ("Ver más", "Cargar más", "Mostrar más"):
            for _ in range(5):
                btn = page.get_by_role("button", name=re.compile(label, re.I))
                if await btn.count() == 0:
                    break
                try:
                    await btn.first.click(timeout=2000)
                    await page.wait_for_timeout(900)
                except Exception:
                    break
        text = await page.inner_text("body")
        hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        return Page(url, True, text=re.sub(r"\n{3,}", "\n\n", text), links=sorted(set(hrefs)))
    except Exception as e:  # noqa: BLE001
        return Page(url, False, error=f"{type(e).__name__}: {e}"[:300])
    finally:
        await page.close()


async def fetch_provider(inicio: list[str], seguir: str | None, max_detalle: int) -> list[Page]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(user_agent=UA, locale="es-CL", timezone_id="America/Santiago")
        pages = [await _grab(ctx, u) for u in inicio]
        if seguir:
            hosts = {urlparse(u).netloc for u in inicio}
            seen = set(inicio)
            detail = []
            for p in pages:
                for href in p.links:
                    href = urljoin(p.url, href).split("#")[0]
                    if urlparse(href).netloc in hosts and seguir in href and href not in seen:
                        seen.add(href)
                        detail.append(href)
            sem = asyncio.Semaphore(4)

            async def one(u):
                async with sem:
                    return await _grab(ctx, u, 30000)

            pages += await asyncio.gather(*(one(u) for u in detail[:max_detalle]))
        await browser.close()
        return pages
