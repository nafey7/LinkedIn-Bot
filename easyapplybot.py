from __future__ import annotations

import json
import csv
import logging
import os
import random
import re
import time
from datetime import datetime, timedelta
import getpass
from pathlib import Path

import pandas as pd
import pyautogui
import yaml
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager


log = logging.getLogger(__name__)


def setupLogger() -> None:
    dt: str = datetime.strftime(datetime.now(), "%m_%d_%y %H_%M_%S ")

    if not os.path.isdir('./logs'):
        os.mkdir('./logs')

    # TODO need to check if there is a log dir available or not
    logging.basicConfig(filename=('./logs/' + str(dt) + 'applyJobs.log'), filemode='w',
                        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s', datefmt='./logs/%d-%b-%y %H:%M:%S')
    log.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
    c_handler.setFormatter(c_format)
    log.addHandler(c_handler)


class EasyApplyBot:
    setupLogger()
    # MAX_SEARCH_TIME is 10 hours by default, feel free to modify it
    MAX_SEARCH_TIME = 60 * 60

    def __init__(self,
                 username,
                 password,
                 phone_number,
                 # profile_path,
                 salary,
                 rate,
                 uploads={},
                 filename='output.csv',
                 blacklist=[],
                 blackListTitles=[],
                 experience_level=[]
                 ) -> None:

        log.info("Welcome to Easy Apply Bot")
        dirpath: str = os.getcwd()
        log.info("current directory is : " + dirpath)
        log.info("Please wait while we prepare the bot for you")
        if experience_level:
            experience_levels = {
                1: "Entry level",
                2: "Associate",
                3: "Mid-Senior level",
                4: "Director",
                5: "Executive",
                6: "Internship"
            }
            applied_levels = [experience_levels[level] for level in experience_level]
            log.info("Applying for experience level roles: " + ", ".join(applied_levels))
        else:
            log.info("Applying for all experience levels")
        

        self.uploads = uploads
        self.salary = salary
        self.rate = rate
        # self.profile_path = profile_path
        past_ids: list | None = self.get_appliedIDs(filename)
        self.appliedJobIDs: list = past_ids if past_ids != None else []
        self.filename: str = filename
        self.options = self.browser_options()
        self.browser = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=self.options)
        self.wait = WebDriverWait(self.browser, 30)
        self.blacklist = blacklist
        self.blackListTitles = blackListTitles
        self.start_linkedin(username, password)
        self.phone_number = phone_number
        self.experience_level = experience_level
        self.shadow_host_selector = None  # Will store the shadow host selector where modal is found


        self.locator = {
            "next": (By.CSS_SELECTOR, "button[aria-label='Continue to next step']"),
            "next_generic": (By.XPATH, "//button[contains(text(), 'Next')]"),  # Generic Next button by text
            "review": (By.CSS_SELECTOR, "button[aria-label='Review your application']"),
            "submit": (By.CSS_SELECTOR, "button[aria-label='Submit application']"),
            "error": (By.CLASS_NAME, "artdeco-inline-feedback__message"),
            "upload_resume": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]"),
            "upload_cv": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]"),
            "follow": (By.CSS_SELECTOR, "label[for='follow-company-checkbox']"),
            "upload": (By.NAME, "file"),
            "search": (By.CLASS_NAME, "jobs-search-results-list"),
            "links": ("xpath", '//div[@data-job-id]'),
            "fields": (By.CLASS_NAME, "jobs-easy-apply-form-section__grouping"),
            "radio_select": (By.CSS_SELECTOR, "input[type='radio']"), #need to append [value={}].format(answer)
            "multi_select": (By.XPATH, "//*[contains(@id, 'text-entity-list-form-component')]"),
            "text_select": (By.CLASS_NAME, "artdeco-text-input--input"),
            "2fa_oneClick": (By.ID, 'reset-password-submit-button'),
            "easy_apply_button": (By.XPATH, '//button[contains(@aria-label, "Easy Apply") and contains(@class, "jobs-apply-button")]'),
            "easy_apply_button_a": (By.XPATH, '//a[contains(@data-view-name, "job-apply-button") and contains(.//span, "Easy Apply")]'),

        }

        #initialize questions and answers file
        self.qa_file = Path("qa.csv")
        self.answers = {}

        #if qa file does not exist, create it
        if self.qa_file.is_file():
            df = pd.read_csv(self.qa_file)
            for index, row in df.iterrows():
                self.answers[row['Question']] = row['Answer']
        #if qa file does exist, load it
        else:
            df = pd.DataFrame(columns=["Question", "Answer"])
            df.to_csv(self.qa_file, index=False, encoding='utf-8')


    def get_appliedIDs(self, filename) -> list | None:
        try:
            df = pd.read_csv(filename,
                             header=None,
                             names=['timestamp', 'jobID', 'job', 'company', 'attempted', 'result'],
                             lineterminator='\n',
                             encoding='utf-8')

            df['timestamp'] = pd.to_datetime(df['timestamp'], format="%Y-%m-%d %H:%M:%S")
            df = df[df['timestamp'] > (datetime.now() - timedelta(days=2))]
            jobIDs: list = list(df.jobID)
            log.info(f"{len(jobIDs)} jobIDs found")
            return jobIDs
        except Exception as e:
            log.info(str(e) + "   jobIDs could not be loaded from CSV {}".format(filename))
            return None

    def browser_options(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        #options.add_argument(r'--remote-debugging-port=9222')
        #options.add_argument(r'--profile-directory=Person 1')

        # Disable webdriver flags or you will be easily detectable
        options.add_argument("--disable-blink-features")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Load user profile
        #options.add_argument(r"--user-data-dir={}".format(self.profile_path))
        return options

    def start_linkedin(self, username, password) -> None:
        log.info("Logging in.....Please wait :)  ")
        self.browser.get("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")
        try:
            # Wait for username and password fields
            user_field = self.wait.until(EC.presence_of_element_located((By.ID, "username")))
            pw_field = self.wait.until(EC.presence_of_element_located((By.ID, "password")))

            # Older selectors retained for future reference:
            # (By.XPATH, '//*[@id="organic-div"]/form/div[3]/button')
            # (By.XPATH, '//button[@type="submit" and contains(@class, "btn-primary")]')
            # (By.XPATH, '//button[contains(text(), "Sign in")]')
            # (By.CSS_SELECTOR, 'button[type="submit"]')

            # Best selectors for the current Sign in button
            login_button = None
            login_selectors = [
                (By.CSS_SELECTOR, 'button[data-litms-control-urn="login-submit"]'),  # most robust
                (By.CSS_SELECTOR, 'button.btn__primary--large[type="submit"]'),     # specific by type and class
                (By.XPATH, '//button[contains(text(), "Sign in")]'),               # fallback: visible text
                (By.CSS_SELECTOR, 'button[type="submit"]'),                        # generic fallback
            ]
            for selector in login_selectors:
                try:
                    login_button = self.wait.until(EC.element_to_be_clickable(selector))
                    break
                except TimeoutException:
                    continue
            if login_button is None:
                raise TimeoutException("Login button not found with any selector!")

            user_field.send_keys(username)
            user_field.send_keys(Keys.TAB)
            time.sleep(1)
            pw_field.send_keys(password)
            time.sleep(1)
            login_button.click()
            time.sleep(5)  # enough time for redirect/2FA if needed
        except TimeoutException as e:
            log.error(f"TimeoutException! Username/password field or login button not found: {e}")
            raise
        except Exception as e:
            log.error(f"Error during login: {e}")
            raise

    def fill_data(self) -> None:
        self.browser.set_window_size(1, 1)
        self.browser.set_window_position(2000, 2000)

    def start_apply(self, positions, locations) -> None:
        start: float = time.time()
        self.fill_data()
        self.positions = positions
        self.locations = locations
        combos: list = []
        while len(combos) < len(positions) * len(locations):
            position = positions[random.randint(0, len(positions) - 1)]
            location = locations[random.randint(0, len(locations) - 1)]
            combo: tuple = (position, location)
            if combo not in combos:
                combos.append(combo)
                log.info(f"Applying to {position}: {location}")
                location = "&location=" + location
                self.applications_loop(position, location)
            if len(combos) > 500:
                break

    # self.finish_apply() --> this does seem to cause more harm than good, since it closes the browser which we usually don't want, other conditions will stop the loop and just break out

    def applications_loop(self, position, location):

        count_application = 0
        count_job = 0
        jobs_per_page = 0
        start_time: float = time.time()

        log.info("Looking for jobs.. Please wait..")

        self.browser.set_window_position(1, 1)
        self.browser.maximize_window()
        self.browser, _ = self.next_jobs_page(position, location, jobs_per_page, experience_level=self.experience_level)
        log.info("Looking for jobs.. Please wait..")

        while time.time() - start_time < self.MAX_SEARCH_TIME:
            try:
                log.info(f"{(self.MAX_SEARCH_TIME - (time.time() - start_time)) // 60} minutes left in this search")

                # sleep to make sure everything loads, add random to make us look human.
                randoTime: float = random.uniform(1.5, 2.9)
                log.debug(f"Sleeping for {round(randoTime, 1)}")
                #time.sleep(randoTime)
                self.load_page(sleep=0.5)

                # LinkedIn displays the search results in a scrollable <div> on the left side, we have to scroll to its bottom

                # scroll to bottom

                if self.is_present(self.locator["search"]):
                    scrollresults = self.get_elements("search")
                    #     self.browser.find_element(By.CLASS_NAME,
                    #     "jobs-search-results-list"
                    # )
                    # Selenium only detects visible elements; if we scroll to the bottom too fast, only 8-9 results will be loaded into IDs list
                    for i in range(300, 3000, 100):
                        self.browser.execute_script("arguments[0].scrollTo(0, {})".format(i), scrollresults[0])
                    scrollresults = self.get_elements("search")
                    #time.sleep(1)

                # get job links, (the following are actually the job card objects)
                if self.is_present(self.locator["links"]):
                    links = self.get_elements("links")
                # links = self.browser.find_elements("xpath",
                #     '//div[@data-job-id]'
                # )

                    jobIDs = {} #{Job id: processed_status}
                
                    # children selector is the container of the job cards on the left
                    for link in links:
                            if 'Applied' not in link.text: #checking if applied already
                                if link.text not in self.blacklist: #checking if blacklisted
                                    jobID = link.get_attribute("data-job-id")
                                    if jobID == "search":
                                        log.debug("Job ID not found, search keyword found instead? {}".format(link.text))
                                        continue
                                    else:
                                        jobIDs[jobID] = "To be processed"
                    if len(jobIDs) > 0:
                        self.apply_loop(jobIDs)
                    self.browser, jobs_per_page = self.next_jobs_page(position,
                                                                      location,
                                                                      jobs_per_page, 
                                                                      experience_level=self.experience_level)
                else:
                    self.browser, jobs_per_page = self.next_jobs_page(position,
                                                                      location,
                                                                      jobs_per_page, 
                                                                      experience_level=self.experience_level)


            except Exception as e:
                print(e)
    def apply_loop(self, jobIDs):
        for jobID in jobIDs:
            if jobIDs[jobID] == "To be processed":
                applied = self.apply_to_job(jobID)
                if applied:
                    log.info(f"Applied to {jobID}")
                else:
                    log.info(f"Failed to apply to {jobID}")
                jobIDs[jobID] == applied

    def apply_to_job(self, jobID):
        # #self.avoid_lock() # annoying

        # get job page
        self.get_job_page(jobID)

        # let page load
        time.sleep(1)

        # get easy apply button
        button = self.get_easy_apply_button()


        # word filter to skip positions not wanted
        if button is not False:
            if any(word in self.browser.title for word in blackListTitles):
                log.info('skipping this application, a blacklisted keyword was found in the job position')
                string_easy = "* Contains blacklisted keyword"
                result = False
            else:
                string_easy = "* has Easy Apply Button"
                log.info("Clicking the EASY apply button")
                
                # Verify button state before clicking and capture screenshot
                try:
                    # Capture screenshot before clicking
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    screenshot_before = f"logs/screenshot_before_click_{timestamp}.png"
                    self.browser.save_screenshot(screenshot_before)
                    log.info(f"Screenshot captured before click: {screenshot_before}")
                    
                    log.debug(f"Button state: displayed={button.is_displayed()}, enabled={button.is_enabled()}")
                    log.debug(f"Button location: {button.location}, size: {button.size}")
                    log.debug(f"Button classes: {button.get_attribute('class')}")
                    log.debug(f"Button aria-label: {button.get_attribute('aria-label')}")
                    log.debug(f"Button text: {button.text}")
                    
                    if not button.is_displayed():
                        log.warning("Button is not displayed, scrolling into view")
                        self.browser.execute_script("arguments[0].scrollIntoView(true);", button)
                        time.sleep(0.5)
                except Exception as e:
                    log.debug(f"Error checking button state: {e}")
                
                # Try multiple click methods
                clicked = False
                try:
                    # Method 1: Native Selenium click
                    button.click()
                    clicked = True
                    log.info("Used native Selenium click")
                    
                    # Capture screenshot after successful click
                    screenshot_after = f"logs/screenshot_after_click_{timestamp}.png"
                    self.browser.save_screenshot(screenshot_after)
                    log.info(f"Screenshot captured after click: {screenshot_after}")
                except Exception as click_error:
                    log.debug(f"Native click failed: {click_error}")
                    try:
                        # Method 2: JavaScript click
                        self.browser.execute_script('arguments[0].click()', button)
                        clicked = True
                        log.info("Used JavaScript click")
                        
                        # Capture screenshot after JavaScript click
                        screenshot_after = f"logs/screenshot_after_click_{timestamp}.png"
                        self.browser.save_screenshot(screenshot_after)
                        log.info(f"Screenshot captured after click: {screenshot_after}")
                    except Exception as js_error:
                        log.debug(f"JavaScript click failed: {js_error}")
                        try:
                            # Method 3: ActionChains click
                            from selenium.webdriver.common.action_chains import ActionChains
                            ActionChains(self.browser).move_to_element(button).click().perform()
                            clicked = True
                            log.info("Used ActionChains click")
                            
                            # Capture screenshot after ActionChains click
                            screenshot_after = f"logs/screenshot_after_click_{timestamp}.png"
                            self.browser.save_screenshot(screenshot_after)
                            log.info(f"Screenshot captured after click: {screenshot_after}")
                        except Exception as action_error:
                            log.error(f"All click methods failed: {action_error}")
                
                # Capture screenshot after any click attempt or if all methods failed
                try:
                    screenshot_final = f"logs/screenshot_final_state_{timestamp}.png"
                    self.browser.save_screenshot(screenshot_final)
                    if clicked:
                        log.info(f"Final screenshot captured: {screenshot_final}")
                    else:
                        log.warning(f"Final screenshot after failed click attempts: {screenshot_final}")
                except Exception as screenshot_error:
                    log.debug(f"Failed to capture final screenshot: {screenshot_error}")
                
                if clicked:
                    log.info("Successfully clicked Easy Apply button")
                else:
                    log.error("Failed to click Easy Apply button")
                clicked = True
                
                # CRITICAL: Wait for the modal to actually appear using WebDriverWait
                log.info("Waiting for modal to appear...")
                
                # Check for and dismiss blocking overlays/popups that prevent modal from opening
                try:
                    log.info("Checking for blocking overlays/popups...")
                    
                    # Common overlay selectors on LinkedIn
                    overlay_selectors = [
                        "button[aria-label='Dismiss']",
                        "button.artdeco-modal__dismiss",
                        ".artdeco-toast",
                        "button[data-tracking-control-name='dismiss']",
                        ".msg-overlay-bubble-header__controls button",
                        # Check for any modal or overlay that might be blocking
                        "div[role='alert']",
                        "div.artdeco-overlay",
                    ]
                    
                    for overlay_selector in overlay_selectors:
                        try:
                            overlays = self.browser.find_elements(By.CSS_SELECTOR, overlay_selector)
                            if overlays:
                                log.info(f"Found {len(overlays)} overlay element(s) with selector: {overlay_selector}")
                                for overlay in overlays:
                                    if overlay.is_displayed():
                                        try:
                                            overlay.click()
                                            log.info("Dismissed blocking overlay")
                                            time.sleep(0.5)
                                        except:
                                            log.debug("Could not click overlay, trying JavaScript click")
                                            try:
                                                self.browser.execute_script('arguments[0].click()', overlay)
                                                log.info("Dismissed blocking overlay via JavaScript")
                                                time.sleep(0.5)
                                            except:
                                                log.debug("Failed to dismiss overlay")
                        except Exception as overlay_error:
                            log.debug(f"Error checking overlay selector {overlay_selector}: {overlay_error}")
                    
                    # Check for ESC key-needed popups or notifications
                    try:
                        # Press ESC to dismiss any keyboard-trapped overlays
                        from selenium.webdriver.common.keys import Keys
                        self.browser.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                        log.debug("Pressed ESC to dismiss any overlays")
                        time.sleep(0.5)
                    except:
                        pass
                        
                except Exception as e:
                    log.debug(f"Error during overlay check: {e}")
                
                # Try to wait for modal appearance using WebDriverWait
                modal_wait = WebDriverWait(self.browser, 10)
                modal_detected_via_wait = False
                modal_selectors = [
                    (By.CSS_SELECTOR, "div[role='dialog']"),
                    (By.CSS_SELECTOR, ".jobs-easy-apply-modal"),
                    (By.CSS_SELECTOR, "div[data-test-modal]")
                ]
                
                for selector in modal_selectors:
                    try:
                        element = modal_wait.until(EC.presence_of_element_located(selector))
                        if element:
                            log.info(f"Modal detected via WebDriverWait with selector: {selector[1]}")
                            modal_detected_via_wait = True
                            break
                    except TimeoutException:
                        log.debug(f"Timeout waiting for modal with selector: {selector[1]}")
                        continue
                
                if not modal_detected_via_wait:
                    log.warning("Modal not detected via WebDriverWait, checking manually...")
                    time.sleep(2)  # Fallback sleep
                
                # Check for shadow DOM - this is where LinkedIn renders the modal
                log.info("Checking for Shadow DOM...")
                shadow_hosts = self.find_all_shadow_hosts()
                
                # Try common shadow host locations
                common_shadow_selectors = [
                    "div[id='interop-outlet']",
                    "div[data-testid='interop-outlet']",
                    "#interop-outlet"
                ]
                
                modal_in_shadow_dom = False
                for selector in common_shadow_selectors:
                    try:
                        log.info(f"Checking shadow host: {selector}")
                        dialogs_in_shadow = self.find_in_shadow_dom(selector, "div[role='dialog']")
                        modals_in_shadow = self.find_in_shadow_dom(selector, ".jobs-easy-apply-modal")
                        modal_data_in_shadow = self.find_in_shadow_dom(selector, "div[data-test-modal]")
                        
                        if dialogs_in_shadow or modals_in_shadow or modal_data_in_shadow:
                            log.info(f"*** MODAL FOUND IN SHADOW DOM at {selector}! ***")
                            modal_in_shadow_dom = True
                            self.shadow_host_selector = selector  # Store for later use
                            break
                        
                        # Additional check: Look for buttons in shadow DOM
                        buttons_in_shadow = self.find_in_shadow_dom(selector, "button")
                        if buttons_in_shadow:
                            log.info(f"Found {len(buttons_in_shadow)} buttons in shadow DOM at {selector}")
                            for btn in buttons_in_shadow[:5]:  # Check first 5 buttons
                                try:
                                    btn_text = self.browser.execute_script('return arguments[0].textContent', btn)
                                    btn_aria = self.browser.execute_script('return arguments[0].getAttribute("aria-label")', btn)
                                    log.info(f"  Shadow button: text='{btn_text.strip()[:50]}', aria-label='{btn_aria}'")
                                except:
                                    pass
                            # If we found buttons but not a modal, maybe the modal is inside a nested structure
                            # Try looking for any div that might be a modal container
                            all_divs = self.browser.execute_script("""
                                var shadowHost = arguments[0];
                                var shadowRoot = shadowHost.shadowRoot;
                                if (shadowRoot) {
                                    return Array.from(shadowRoot.querySelectorAll('div'));
                                }
                                return [];
                            """, self.browser.find_element(By.CSS_SELECTOR, selector))
                            log.info(f"Found {len(all_divs)} divs in shadow DOM")
                            
                    except Exception as e:
                        log.debug(f"Error checking {selector}: {e}")
                
                # Additional wait for page to fully load (reduced from 5 to 1 second since we already used WebDriverWait)
                time.sleep(1)
                
                # Check for modal presence with better detection
                modal_detected = False
                dialogs = self.browser.find_elements(By.CSS_SELECTOR, "div[role='dialog']")
                log.info(f"Found {len(dialogs)} dialog elements")
                
                # Also check for the specific modal classes
                try:
                    modal_by_class = self.browser.find_elements(By.CSS_SELECTOR, ".jobs-easy-apply-modal")
                    log.info(f"Found {len(modal_by_class)} elements with .jobs-easy-apply-modal class")
                    if modal_by_class:
                        for modal in modal_by_class:
                            is_displayed = modal.is_displayed()
                            log.info(f"Modal: displayed={is_displayed}, visible={modal.get_attribute('style')}")
                            if is_displayed:
                                modal_detected = True
                except Exception as e:
                    log.debug(f"Error checking modal by class: {e}")
                
                # Check for the specific data attribute
                try:
                    modal_by_data = self.browser.find_elements(By.CSS_SELECTOR, "div[data-test-modal]")
                    log.info(f"Found {len(modal_by_data)} elements with data-test-modal")
                    if modal_by_data:
                        for modal in modal_by_data:
                            if modal.is_displayed():
                                modal_detected = True
                except Exception as e:
                    log.debug(f"Error checking modal by data: {e}")
                
                if len(dialogs) > 0 or modal_detected:
                    log.info(f"Modal detected! Found {len(dialogs)} dialog(s)")
                    modal_detected = True
                
                # Additional detailed check for debugging
                try:
                    dialogs = self.browser.find_elements(By.CSS_SELECTOR, "div[role='dialog']")
                    log.info(f"Immediate check: Found {len(dialogs)} dialog elements")
                    if dialogs:
                        for i, dialog in enumerate(dialogs):
                            log.info(f"Dialog {i}: displayed={dialog.is_displayed()}, text={dialog.text[:100]}")
                    
                    # Check iframes - the modal might be inside one
                    iframes = self.browser.find_elements(By.TAG_NAME, "iframe")
                    log.info(f"Found {len(iframes)} iframes")
                    
                    # Look for the specific interop iframe
                    interop_iframe = None
                    try:
                        interop_iframe = self.browser.find_element(By.CSS_SELECTOR, "iframe[data-testid='interop-iframe']")
                        log.info("Found interop-iframe")
                    except:
                        log.info("No interop-iframe found")
                    
                    # Store info about which iframe might contain the modal
                    modal_iframe_index = None
                    
                    for i, iframe in enumerate(iframes):
                        try:
                            # Try to get the iframe src to see what it contains
                            src = iframe.get_attribute("src")
                            data_testid = iframe.get_attribute("data-testid")
                            log.info(f"Iframe {i}: src={src}, data-testid={data_testid}, visible={iframe.is_displayed()}")
                            
                            # Try switching to the iframe
                            self.browser.switch_to.frame(iframe)
                            
                            # Check for dialog in iframe first (this is the key)
                            dialogs_in_iframe = self.browser.find_elements(By.CSS_SELECTOR, "div[role='dialog']")
                            if dialogs_in_iframe:
                                log.info(f"  *** Found {len(dialogs_in_iframe)} dialog(s) in iframe {i}! ***")
                                modal_iframe_index = i
                                for j, dialog in enumerate(dialogs_in_iframe):
                                    log.info(f"    Dialog {j}: text={dialog.text[:100] if dialog.text else 'empty'}")
                            
                            buttons_in_iframe = self.browser.find_elements(By.TAG_NAME, "button")
                            log.info(f"  Buttons in iframe {i}: {len(buttons_in_iframe)}")
                            
                            # Look specifically for "Next" button
                            next_found = False
                            for btn in buttons_in_iframe[:15]:
                                aria_label = btn.get_attribute("aria-label")
                                if aria_label and "next" in aria_label.lower():
                                    log.info(f"    *** Found Next button! ***")
                                    log.info(f"    Button: text='{btn.text}', aria-label='{aria_label}'")
                                    next_found = True
                            
                            if not next_found and buttons_in_iframe:
                                # Log first few buttons anyway
                                for btn in buttons_in_iframe[:5]:
                                    log.info(f"    Button: text='{btn.text}', aria-label='{btn.get_attribute('aria-label')}'")
                            
                            self.browser.switch_to.default_content()
                        except Exception as iframe_e:
                            log.info(f"  Could not access iframe {i}: {iframe_e}")
                            try:
                                self.browser.switch_to.default_content()
                            except:
                                pass
                    
                    if modal_iframe_index is not None:
                        log.info(f"Modal is likely in iframe {modal_iframe_index}")
                except Exception as e:
                    log.debug(f"Error in immediate check: {e}")
                
                # Wait for modal to appear with multiple attempts
                modal_present = False
                for attempt in range(3):
                    try:
                        # Try multiple modal selectors
                        modal_selectors = [
                            "div[data-test-modal]",
                            ".jobs-easy-apply-modal",
                            ".artdeco-modal",
                            "div[role='dialog']",
                            ".jobs-easy-apply-modal__content"
                        ]
                        
                        for selector in modal_selectors:
                            try:
                                element = self.browser.find_element(By.CSS_SELECTOR, selector)
                                if element.is_displayed():
                                    modal_present = True
                                    log.info(f"Modal detected successfully with selector: {selector}")
                                    break
                            except:
                                pass
                        
                        if modal_present:
                            break
                        
                        # Debug: Check what's in the page source
                        if attempt == 0:
                            log.debug(f"Page title: {self.browser.title}")
                            log.debug(f"Current URL: {self.browser.current_url}")
                            # Check for common elements
                            try:
                                dialogs = self.browser.find_elements(By.CSS_SELECTOR, "div[role='dialog']")
                                log.debug(f"Found {len(dialogs)} dialog elements")
                                buttons = self.browser.find_elements(By.TAG_NAME, "button")
                                log.debug(f"Total buttons on page: {len(buttons)}")
                                
                                # Check if any buttons have "Next" text
                                for btn in buttons[:10]:  # Check first 10 buttons
                                    btn_text = btn.text
                                    aria_label = btn.get_attribute("aria-label")
                                    if btn_text and "Next" in btn_text:
                                        log.debug(f"Found button with 'Next' text: '{btn_text}' with aria-label: '{aria_label}'")
                                    
                                # Check for iframes
                                iframes = self.browser.find_elements(By.TAG_NAME, "iframe")
                                log.debug(f"Found {len(iframes)} iframes on the page")
                                
                            except Exception as e:
                                log.debug(f"Error checking page: {e}")
                        
                        time.sleep(2)
                        log.debug(f"Waiting for modal... attempt {attempt + 1}/5")
                    except Exception as e:
                        log.debug(f"Error during modal detection: {e}")
                        time.sleep(2)
                
                if not modal_present:
                    log.warning("Modal not detected after waiting, proceeding anyway")
                    log.info("Proceeding to fill out fields...")
                
                time.sleep(2)  # Additional wait for form to fully render
                self.fill_out_fields()
                result: bool = self.send_resume()
                if result:
                    string_easy = "*Applied: Sent Resume"
                else:
                    string_easy = "*Did not apply: Failed to send Resume"
        elif "You applied on" in self.browser.page_source:
            log.info("You have already applied to this position.")
            string_easy = "* Already Applied"
            result = False
        else:
            log.info("The Easy apply button does not exist.")
            string_easy = "* Doesn't have Easy Apply Button"
            result = False


        # position_number: str = str(count_job + jobs_per_page)
        log.info(f"\nPosition {jobID}:\n {self.browser.title} \n {string_easy} \n")

        self.write_to_file(button, jobID, self.browser.title, result)
        return result

    def write_to_file(self, button, jobID, browserTitle, result) -> None:
        def re_extract(text, pattern):
            target = re.search(pattern, text)
            if target:
                target = target.group(1)
            return target

        timestamp: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attempted: bool = False if button == False else True
        job = re_extract(browserTitle.split(' | ')[0], r"\(?\d?\)?\s?(\w.*)")
        company = re_extract(browserTitle.split(' | ')[1], r"(\w.*)")

        toWrite: list = [timestamp, jobID, job, company, attempted, result]
        with open(self.filename, 'a+') as f:
            writer = csv.writer(f)
            writer.writerow(toWrite)

    def get_job_page(self, jobID):

        job: str = 'https://www.linkedin.com/jobs/view/' + str(jobID)
        self.browser.get(job)
        self.job_page = self.load_page(sleep=0.5)
        return self.job_page

    def get_easy_apply_button(self):
        EasyApplyButton = False
        try:
            buttons = self.get_elements("easy_apply_button")
            buttons_a = self.get_elements("easy_apply_button_a")
            all_buttons = buttons + buttons_a
            for button in all_buttons:
                if "Easy Apply" in button.text:
                    EasyApplyButton = button
                    self.wait.until(EC.element_to_be_clickable(EasyApplyButton))
                    break
                else:
                    log.debug("Easy Apply button not found")
        except Exception as e: 
            print("Exception:",e)
            log.debug("Easy Apply button not found")

        return EasyApplyButton

    def fill_out_fields(self):
        log.info("Filling out contact info fields")
        
        # Wait for the form to be fully loaded
        time.sleep(1)
        
        # Handle mobile phone number input (email and country code are auto-filled by LinkedIn)
        try:
            inputs = self.browser.find_elements(By.TAG_NAME, "input")
            for input_elem in inputs:
                input_id = input_elem.get_attribute("id") or ""
                # Check if this is the phone number input
                if "phoneNumber-nationalNumber" in input_id:
                    input_elem.clear()
                    # Remove +92 prefix if present since country code is selected separately
                    phone_number = self.phone_number.replace("+92", "").strip()
                    input_elem.send_keys(phone_number)
                    log.info(f"Entered phone number: {phone_number}")
                    break
        except Exception as e:
            log.debug(f"Could not enter phone number: {e}")

        return


    def get_elements(self, type) -> list:
        elements = []
        element = self.locator[type]
        if self.is_present(element):
            elements = self.browser.find_elements(element[0], element[1])
        
        # If no elements found in main document and we have a shadow host, search shadow DOM
        if len(elements) == 0 and self.shadow_host_selector:
            try:
                elements = self.find_in_shadow_dom(self.shadow_host_selector, element[1])
                if elements:
                    log.info(f"Found {len(elements)} {type} element(s) in shadow DOM")
            except Exception as e:
                log.debug(f"Error searching for {type} in shadow DOM: {e}")
        
        return elements

    def is_present(self, locator):
        return len(self.browser.find_elements(locator[0],
                                              locator[1])) > 0

    def find_in_shadow_dom(self, shadow_host_selector, target_selector):
        """Find elements inside shadow DOM"""
        try:
            shadow_host = self.browser.find_element(By.CSS_SELECTOR, shadow_host_selector)
            shadow_root = self.browser.execute_script('return arguments[0].shadowRoot', shadow_host)
            if shadow_root:
                elements = self.browser.execute_script(
                    'return arguments[0].querySelectorAll(arguments[1])', 
                    shadow_root, target_selector
                )
                log.debug(f"Found {len(elements)} elements in shadow DOM with selector '{target_selector}'")
                
                # Debug: Log what's actually inside the shadow root
                if len(elements) == 0 and target_selector == "div[role='dialog']":
                    all_elements = self.browser.execute_script('return arguments[0].querySelectorAll("*")', shadow_root)
                    log.debug(f"Shadow DOM contains {len(all_elements)} total elements")
                    if len(all_elements) > 0:
                        first_20 = all_elements[:20]
                        for elem in first_20:
                            tag = self.browser.execute_script('return arguments[0].tagName', elem)
                            log.debug(f"  Element in shadow: {tag}")
                
                return elements
        except Exception as e:
            log.debug(f"Error accessing shadow DOM with '{shadow_host_selector}': {e}")
        return []

    def find_all_shadow_hosts(self):
        """Find all elements on page that have a shadow root"""
        try:
            shadow_hosts_info = self.browser.execute_script("""
                return Array.from(document.querySelectorAll('*'))
                    .filter(el => el.shadowRoot)
                    .map(el => {
                        return {
                            tagName: el.tagName,
                            id: el.id,
                            className: el.className,
                            dataTestId: el.getAttribute('data-testid'),
                            outerHTML: el.outerHTML.substring(0, 200)
                        };
                    });
            """)
            log.info(f"Found {len(shadow_hosts_info)} shadow hosts on page")
            for i, host_info in enumerate(shadow_hosts_info):
                log.info(f"Shadow host {i}: tag={host_info.get('tagName')}, id={host_info.get('id')}, data-testid={host_info.get('dataTestId')}")
            return shadow_hosts_info
        except Exception as e:
            log.debug(f"Error finding shadow hosts: {e}")
        return []

    def send_resume(self) -> bool:
        def is_present(button_locator) -> bool:
            return len(self.browser.find_elements(button_locator[0],
                                                  button_locator[1])) > 0

        try:
            #time.sleep(random.uniform(1.5, 2.5))
            next_locator = (By.CSS_SELECTOR,
                            "button[aria-label='Continue to next step']")
            review_locator = (By.CSS_SELECTOR,
                              "button[aria-label='Review your application']")
            submit_locator = (By.CSS_SELECTOR,
                              "button[aria-label='Submit application']")
            error_locator = (By.CLASS_NAME,"artdeco-inline-feedback__message")
            upload_resume_locator = (By.XPATH, '//span[text()="Upload resume"]')
            upload_cv_locator = (By.XPATH, '//span[text()="Upload cover letter"]')
            # WebElement upload_locator = self.browser.find_element(By.NAME, "file")
            follow_locator = (By.CSS_SELECTOR, "label[for='follow-company-checkbox']")

            submitted = False
            loop = 0
            while loop < 10:
                log.debug(f"Loop iteration: {loop}")
                loop += 1
                time.sleep(1)
                
                # Debug: Check what elements are present
                log.debug(f"Checking elements - upload_resume: {is_present(upload_resume_locator)}, "
                         f"upload_cv: {is_present(upload_cv_locator)}, "
                         f"submit: {len(self.get_elements('submit'))}, "
                         f"error: {len(self.get_elements('error'))}, "
                         f"next: {len(self.get_elements('next'))}, "
                         f"review: {len(self.get_elements('review'))}, "
                         f"follow: {len(self.get_elements('follow'))}")
                
                # Debug: Try to find next button with multiple selectors
                if loop == 1:  # Only log this on first iteration to avoid spam
                    try:
                        all_buttons = self.browser.find_elements(By.TAG_NAME, "button")
                        log.debug(f"Total buttons found on page: {len(all_buttons)}")
                        for btn in all_buttons:
                            aria_label = btn.get_attribute("aria-label")
                            if aria_label:
                                log.debug(f"Button aria-label: '{aria_label}'")
                        # Also check for the specific next button
                        next_btns = self.browser.find_elements(By.CSS_SELECTOR, "button[aria-label='Continue to next step']")
                        log.debug(f"Found {len(next_btns)} buttons with aria-label='Continue to next step'")
                    except Exception as e:
                        log.debug(f"Error checking buttons: {e}")
                
                # Upload resume
                if is_present(upload_resume_locator):
                    #upload_locator = self.browser.find_element(By.NAME, "file")
                    try:
                        resume_locator = self.browser.find_element(By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]")
                        resume = self.uploads["Resume"]
                        resume_locator.send_keys(resume)
                    except Exception as e:
                        log.error(e)
                        log.error("Resume upload failed")
                        log.debug("Resume: " + resume)
                        log.debug("Resume Locator: " + str(resume_locator))
                # Upload cover letter if possible
                if is_present(upload_cv_locator):
                    cv = self.uploads["Cover Letter"]
                    cv_locator = self.browser.find_element(By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]")
                    cv_locator.send_keys(cv)

                    #time.sleep(random.uniform(4.5, 6.5))
                elif len(self.get_elements("follow")) > 0:
                    elements = self.get_elements("follow")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                if len(self.get_elements("submit")) > 0:
                    elements = self.get_elements("submit")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()
                        log.info("Application Submitted")
                        submitted = True
                        break

                elif len(self.get_elements("error")) > 0:
                    elements = self.get_elements("error")
                    if "application was sent" in self.browser.page_source:
                        log.info("Application Submitted")
                        submitted = True
                        break
                    elif len(elements) > 0:
                        while len(elements) > 0:
                            log.info("Please answer the questions, waiting 5 seconds...")
                            time.sleep(5)
                            elements = self.get_elements("error")

                            for element in elements:
                                self.process_questions()

                            if "application was sent" in self.browser.page_source:
                                log.info("Application Submitted")
                                submitted = True
                                break
                            elif is_present(self.locator["easy_apply_button"]):
                                log.info("Skipping application")
                                submitted = False
                                break
                        continue
                        #add explicit wait
                    
                    else:
                        log.info("Application not submitted")
                        time.sleep(2)
                        break
                    # self.process_questions()

                elif len(self.get_elements("next")) > 0:
                    log.info("Found 'Continue to next step' button - clicking it")
                    elements = self.get_elements("next")
                    log.debug(f"Found {len(elements)} 'next' button(s)")
                    clicked = False
                    for element in elements:
                        try:
                            button = self.wait.until(EC.element_to_be_clickable(element))
                            log.debug(f"Next button is clickable, attempting click")
                            button.click()
                            log.info("Clicked 'Next' button successfully")
                            clicked = True
                            break
                        except Exception as click_error:
                            log.error(f"Failed to click Next button with native click: {click_error}")
                            # Try JavaScript click - required for elements in shadow DOM
                            try:
                                log.info("Trying JavaScript click for Next button")
                                self.browser.execute_script('arguments[0].click()', button)
                                log.info("Clicked Next button using JavaScript")
                                clicked = True
                                break
                            except Exception as js_click_error:
                                log.error(f"JavaScript click also failed: {js_click_error}")
                    
                    if not clicked:
                        # Try alternative selectors if main selector failed
                        try:
                            log.info("Trying alternative selector: button[data-easy-apply-next-button]")
                            alternative_button = self.browser.find_element(By.CSS_SELECTOR, "button[data-easy-apply-next-button]")
                            alternative_button.click()
                            log.info("Clicked Next button using alternative selector")
                            clicked = True
                        except Exception as alt_error:
                            log.error(f"Alternative selector also failed: {alt_error}")
                            try:
                                log.info("Trying alternative selector: button.artdeco-button--primary")
                                primary_buttons = self.browser.find_elements(By.CSS_SELECTOR, "button.artdeco-button--primary")
                                if primary_buttons:
                                    primary_buttons[-1].click()  # Click the last primary button
                                    log.info("Clicked Next button using primary class")
                                    clicked = True
                            except Exception as alt2_error:
                                log.error(f"Third attempt failed: {alt2_error}")
                    
                    if clicked:
                        time.sleep(2)  # Wait for next page to load
                
                elif len(self.get_elements("next_generic")) > 0:
                    log.info("Found 'Next' button by text - clicking it")
                    elements = self.get_elements("next_generic")
                    log.debug(f"Found {len(elements)} generic 'Next' button(s)")
                    clicked = False
                    for element in elements:
                        try:
                            # Only click if it's displayed
                            if element.is_displayed():
                                button = self.wait.until(EC.element_to_be_clickable(element))
                                log.debug(f"Next button is clickable, attempting click")
                                button.click()
                                log.info("Clicked generic 'Next' button successfully")
                                clicked = True
                                break
                        except Exception as click_error:
                            log.debug(f"Failed to click generic Next button: {click_error}")
                            try:
                                self.browser.execute_script('arguments[0].click()', element)
                                log.info("Clicked generic Next button using JavaScript")
                                clicked = True
                                break
                            except:
                                pass
                    
                    if clicked:
                        time.sleep(2)
                
                # Try to click button inside shadow DOM using JavaScript
                if self.shadow_host_selector:
                    try:
                        log.info(f"Attempting to click Next button inside shadow DOM at {self.shadow_host_selector}")
                        # Use JavaScript to find and click the button inside the shadow DOM
                        button_clicked = self.browser.execute_script("""
                            // Find the shadow host
                            var shadowHost = arguments[0];
                            var shadowRoot = shadowHost.shadowRoot;
                            if (shadowRoot) {
                                // Try multiple selectors to find the Next button
                                var button = shadowRoot.querySelector('button[aria-label="Continue to next step"]') ||
                                            shadowRoot.querySelector('button[data-easy-apply-next-button]') ||
                                            shadowRoot.querySelector('button.artdeco-button--primary');
                                if (button) {
                                    // Scroll into view first
                                    button.scrollIntoView({behavior: 'smooth', block: 'center'});
                                    // Dispatch a proper click event
                                    button.click();
                                    return true;
                                }
                            }
                            return false;
                        """, self.browser.find_element(By.CSS_SELECTOR, self.shadow_host_selector))
                        
                        if button_clicked:
                            log.info("Successfully clicked Next button inside shadow DOM via JavaScript")
                            time.sleep(2)
                            continue  # Skip to next loop iteration
                    except Exception as shadow_error:
                        log.debug(f"Failed to click button in shadow DOM: {shadow_error}")
                
                # Try data attribute selector
                try:
                    alt_button = self.browser.find_element(By.CSS_SELECTOR, "button[data-easy-apply-next-button]")
                    if alt_button.is_displayed():
                        log.info("Found Next button using data-easy-apply-next-button attribute")
                        alt_button.click()
                        log.info("Clicked Next button successfully")
                        time.sleep(2)
                        continue  # Skip to next loop iteration
                except Exception as e:
                    log.debug(f"No button with data-easy-apply-next-button: {e}")
                
                # Try artdeco-button--primary class
                try:
                    primary_buttons = self.browser.find_elements(By.CSS_SELECTOR, "button.artdeco-button--primary")
                    displayed_primary = [btn for btn in primary_buttons if btn.is_displayed()]
                    if displayed_primary:
                        log.info(f"Found {len(displayed_primary)} primary buttons, clicking the last one")
                        displayed_primary[-1].click()  # Click the last primary button (usually the Next button)
                        log.info("Clicked Next button using primary class")
                        time.sleep(2)
                        continue  # Skip to next loop iteration
                except Exception as e:
                    log.debug(f"Error with primary buttons: {e}")
                
                # Additional check for any button with aria-label containing "next" or "Continue"
                found_button = False
                try:
                    all_buttons = self.browser.find_elements(By.TAG_NAME, "button")
                    for btn in all_buttons:
                        if not btn.is_displayed():
                            continue
                        aria_label = btn.get_attribute("aria-label")
                        if aria_label and ("next" in aria_label.lower() or "continue" in aria_label.lower()):
                            log.info(f"Found button with aria-label: '{aria_label}'")
                            try:
                                btn.click()
                                log.info("Clicked button successfully")
                                time.sleep(2)
                                found_button = True
                                break  # Exit the for loop
                            except:
                                try:
                                    self.browser.execute_script('arguments[0].click()', btn)
                                    log.info("Clicked button using JavaScript")
                                    time.sleep(2)
                                    found_button = True
                                    break
                                except:
                                    pass
                    # if we found and clicked a button, skip to next iteration
                    if found_button:
                        continue
                except Exception as e:
                    log.debug(f"Error in fallback button search: {e}")

                # Check for review button
                if len(self.get_elements("review")) > 0:
                    elements = self.get_elements("review")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                # Check for follow button
                elif len(self.get_elements("follow")) > 0:
                    elements = self.get_elements("follow")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()
                else:
                    log.debug("No buttons found on this step. Waiting...")
                    # Last resort: search for ANY button with "Next" aria-label
                    try:
                        all_buttons = self.browser.find_elements(By.TAG_NAME, "button")
                        for btn in all_buttons:
                            aria_label = btn.get_attribute("aria-label")
                            btn_text = btn.text.strip()
                            # Look for "Next" button
                            if aria_label and ("next" in aria_label.lower() or "Next" in aria_label):
                                log.info(f"Found Next button with aria-label: '{aria_label}'")
                                try:
                                    btn.click()
                                    log.info("Successfully clicked Next button")
                                    time.sleep(2)
                                    break
                                except:
                                    try:
                                        self.browser.execute_script('arguments[0].click()', btn)
                                        log.info("Clicked Next button with JavaScript")
                                        time.sleep(2)
                                        break
                                    except:
                                        pass
                            elif btn_text and "Next" in btn_text and btn.is_displayed():
                                log.info(f"Found Next button with text: '{btn_text}'")
                                try:
                                    btn.click()
                                    log.info("Successfully clicked Next button")
                                    time.sleep(2)
                                    break
                                except:
                                    try:
                                        self.browser.execute_script('arguments[0].click()', btn)
                                        log.info("Clicked Next button with JavaScript")
                                        time.sleep(2)
                                        break
                                    except:
                                        pass
                    except Exception as e:
                        log.debug(f"Error in fallback Next button search: {e}")
                    
                    time.sleep(2)

        except Exception as e:
            log.error(e)
            log.error("cannot apply to this job")
            pass
            #raise (e)

        return submitted
    def process_questions(self):
        time.sleep(1)
        form = self.get_elements("fields") #self.browser.find_elements(By.CLASS_NAME, "jobs-easy-apply-form-section__grouping")
        for field in form:
            question = field.text
            answer = self.ans_question(question.lower())
            #radio button
            if self.is_present(self.locator["radio_select"]):
                try:
                    input = field.find_element(By.CSS_SELECTOR, "input[type='radio'][value={}]".format(answer))
                    input.execute_script("arguments[0].click();", input)
                except Exception as e:
                    log.error(e)
                    continue
            #multi select
            elif self.is_present(self.locator["multi_select"]):
                try:
                    input = field.find_element(self.locator["multi_select"])
                    input.send_keys(answer)
                except Exception as e:
                    log.error(e)
                    continue
            # text box
            elif self.is_present(self.locator["text_select"]):
                try:
                    input = field.find_element(self.locator["text_select"])
                    input.send_keys(answer)
                except Exception as e:
                    log.error(e)
                    continue

            elif self.is_present(self.locator["text_select"]):
               pass

            if "Yes" or "No" in answer: #radio button
                try: #debug this
                    input = form.find_element(By.CSS_SELECTOR, "input[type='radio'][value={}]".format(answer))
                    form.execute_script("arguments[0].click();", input)
                except:
                    pass


            else:
                input = form.find_element(By.CLASS_NAME, "artdeco-text-input--input")
                input.send_keys(answer)

    def ans_question(self, question): #refactor this to an ans.yaml file
        answer = None
        if "how many" in question:
            answer = "1"
        elif "experience" in question:
            answer = "1"
        elif "sponsor" in question:
            answer = "No"
        elif 'do you ' in question:
            answer = "Yes"
        elif "have you " in question:
            answer = "Yes"
        elif "US citizen" in question:
            answer = "Yes"
        elif "are you " in question:
            answer = "Yes"
        elif "salary" in question:
            answer = self.salary
        elif "can you" in question:
            answer = "Yes"
        elif "gender" in question:
            answer = "Male"
        elif "race" in question:
            answer = "Wish not to answer"
        elif "lgbtq" in question:
            answer = "Wish not to answer"
        elif "ethnicity" in question:
            answer = "Wish not to answer"
        elif "nationality" in question:
            answer = "Wish not to answer"
        elif "government" in question:
            answer = "I do not wish to self-identify"
        elif "are you legally" in question:
            answer = "Yes"
        else:
            log.info("Not able to answer question automatically. Please provide answer")
            #open file and document unanswerable questions, appending to it
            answer = "user provided"
            time.sleep(15)

            # df = pd.DataFrame(self.answers, index=[0])
            # df.to_csv(self.qa_file, encoding="utf-8")
        log.info("Answering question: " + question + " with answer: " + answer)

        # Append question and answer to the CSV
        if question not in self.answers:
            self.answers[question] = answer
            # Append a new question-answer pair to the CSV file
            new_data = pd.DataFrame({"Question": [question], "Answer": [answer]})
            new_data.to_csv(self.qa_file, mode='a', header=False, index=False, encoding='utf-8')
            log.info(f"Appended to QA file: '{question}' with answer: '{answer}'.")

        return answer

    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 4000:
            self.browser.execute_script("window.scrollTo(0," + str(scroll_page) + " );")
            scroll_page += 500
            time.sleep(sleep)

        if sleep != 1:
            self.browser.execute_script("window.scrollTo(0,0);")
            time.sleep(sleep)

        page = BeautifulSoup(self.browser.page_source, "lxml")
        return page

    def avoid_lock(self) -> None:
        x, _ = pyautogui.position()
        pyautogui.moveTo(x + 200, pyautogui.position().y, duration=1.0)
        pyautogui.moveTo(x, pyautogui.position().y, duration=0.5)
        pyautogui.keyDown('ctrl')
        pyautogui.press('esc')
        pyautogui.keyUp('ctrl')
        time.sleep(0.5)
        pyautogui.press('esc')

    def next_jobs_page(self, position, location, jobs_per_page, experience_level=[]):
        # Construct the experience level part of the URL
        experience_level_str = ",".join(map(str, experience_level)) if experience_level else ""
        experience_level_param = f"&f_E={experience_level_str}" if experience_level_str else ""
        self.browser.get(
            # URL for jobs page
            "https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords=" +
            position + location + "&start=" + str(jobs_per_page) + experience_level_param)
        #self.avoid_lock()
        log.info("Loading next job page?")
        self.load_page()
        return (self.browser, jobs_per_page)

    # def finish_apply(self) -> None:
    #     self.browser.close()


if __name__ == '__main__':

    with open("config.yaml", 'r') as stream:
        try:
            parameters = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise exc

    assert len(parameters['positions']) > 0
    assert len(parameters['locations']) > 0
    assert parameters['username'] is not None
    assert parameters['password'] is not None
    assert parameters['phone_number'] is not None


    if 'uploads' in parameters.keys() and type(parameters['uploads']) == list:
        raise Exception("uploads read from the config file appear to be in list format" +
                        " while should be dict. Try removing '-' from line containing" +
                        " filename & path")

    log.info({k: parameters[k] for k in parameters.keys() if k not in ['username', 'password']})

    output_filename: list = [f for f in parameters.get('output_filename', ['output.csv']) if f is not None]
    output_filename: list = output_filename[0] if len(output_filename) > 0 else 'output.csv'
    blacklist = parameters.get('blacklist', [])
    blackListTitles = parameters.get('blackListTitles', [])

    uploads = {} if parameters.get('uploads', {}) is None else parameters.get('uploads', {})
    for key in uploads.keys():
        assert uploads[key] is not None

    locations: list = [l for l in parameters['locations'] if l is not None]
    positions: list = [p for p in parameters['positions'] if p is not None]

    bot = EasyApplyBot(parameters['username'],
                       parameters['password'],
                       parameters['phone_number'],
                       parameters['salary'],
                       parameters['rate'], 
                       uploads=uploads,
                       filename=output_filename,
                       blacklist=blacklist,
                       blackListTitles=blackListTitles,
                       experience_level=parameters.get('experience_level', [])
                       )
    bot.start_apply(positions, locations)


