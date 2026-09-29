"""Exercise the UI in an isolated headless Chrome profile."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image, ImageStat
import io

root=Path(__file__).resolve().parents[1]
with sync_playwright() as playwright:
    browser=playwright.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8765')
    page.wait_for_function("document.querySelector('#tools').textContent.includes('ready')")
    page.locator('#photos').set_input_files([str(file) for file in sorted((root/'.test-data/capture').glob('*.png'))])
    page.wait_for_function("document.querySelector('#selection').textContent.includes('48 photos')")
    page.wait_for_timeout(2000)
    page.screenshot(path=str(root/'.test-data/app-desktop.png'),full_page=True)
    assert page.locator('#selection').inner_text().startswith('48 photos')
    if page.locator('#download').is_visible():
        page.wait_for_function("document.querySelector('#reset-view').disabled === false",timeout=20000)
        page.wait_for_timeout(1500)
        preview=Image.open(io.BytesIO(page.locator('#viewer').screenshot())).convert('RGB')
        assert max(ImageStat.Stat(preview).stddev)>15, 'Preview is blank or transparent'
        page.locator('#rotate-model').click()
        page.locator('#reset-view').click()
        with page.expect_download() as download:
            page.locator('#download').click()
        download.value.save_as(str(root/'.test-data/browser-model.zip'))
        print('Preview controls and model download passed')
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(root/'.test-data/app-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
    browser.close()
    assert not errors, errors
    print('Browser checks passed: photo selection, responsive layout, no JavaScript exceptions.')
