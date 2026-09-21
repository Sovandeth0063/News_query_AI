/**
 * Accessible Tabs Navigation with Roving Tabindex
 */

export function initTabs(onTabChange) {
  const tabList = document.querySelector('[role="tablist"]');
  if (!tabList) return;

  const tabs = Array.from(tabList.querySelectorAll('[role="tab"]'));
  const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));

  function activateTab(tab, triggerCallback = true) {
    // Update tabs
    tabs.forEach(t => {
      const isSelected = t === tab;
      t.setAttribute('aria-selected', isSelected ? 'true' : 'false');
      t.setAttribute('tabindex', isSelected ? '0' : '-1');
      t.classList.toggle('active', isSelected);
    });

    // Update panels
    const targetPanelId = tab.getAttribute('aria-controls');
    panels.forEach(p => {
      const isTarget = p.id === targetPanelId;
      p.hidden = !isTarget;
      p.classList.toggle('active', isTarget);
    });

    if (triggerCallback && typeof onTabChange === 'function') {
      onTabChange(tab.id, targetPanelId);
    }
  }

  // Click handler
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      activateTab(tab);
    });
  });

  // Keyboard navigation (Roving Tabindex)
  tabList.addEventListener('keydown', (e) => {
    const currentTab = document.activeElement;
    const currentIndex = tabs.indexOf(currentTab);
    if (currentIndex === -1) return;

    let targetIndex = null;

    if (e.key === 'ArrowRight') {
      targetIndex = (currentIndex + 1) % tabs.length;
    } else if (e.key === 'ArrowLeft') {
      targetIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    } else if (e.key === 'Home') {
      targetIndex = 0;
    } else if (e.key === 'End') {
      targetIndex = tabs.length - 1;
    }

    if (targetIndex !== null) {
      e.preventDefault();
      tabs[targetIndex].focus();
      activateTab(tabs[targetIndex]);
    }
  });

  // Activate first tab by default
  const activeTab = tabs.find(t => t.getAttribute('aria-selected') === 'true') || tabs[0];
  if (activeTab) {
    activateTab(activeTab, false);
  }
}

export function switchTab(tabId) {
  const tab = document.getElementById(tabId);
  if (tab) {
    tab.click();
  }
}
