/*
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2025 Joshua Vlantis
*/
(function(){
  const linksPrimary = [
    { href:'/', label:'Map', key:'map' },
    { href:'/blog.html', label:'Blog', key:'blog' },
    { href:'/about.html', label:'About', key:'about' }
  ];
  const linksMore = [
    { href:'/updates.html', label:'Updates', key:'updates' },
    { href:'/limits.html', label:'Limits', key:'limits' },
    { href:'/records.html', label:'AUC', key:'auc' },
    { href:'https://github.com/JoshuaVlantis/Wave-Finder', label:'Source (AGPL)', key:'source' },
  ];
  function activeKey(){
    const p = location.pathname;
    if (p === '/' || p === '/index.html') return 'map';
    if (p.includes('/limits')) return 'limits';
    if (p.includes('/blog')) return 'blog';
    if (p.includes('/post')) return 'blog';
    if (p.includes('/about')) return 'about';
    if (p.includes('/records')) return 'auc';
    if (p.includes('/updates')) return 'updates';
    return '';
  }
  function pill(href,label,key){
    const act = activeKey()===key ? 'active' : '';
    return `<a class="wf-pill ${act}" href="${href}">${label}</a>`;
  }
  function buildHeader(){
    const more = linksMore.length ? `
      <div class="wf-more">
        <button class="wf-pill" id="wf-more-btn">More ▾</button>
        <div class="wf-menu" id="wf-more-menu">
          ${linksMore.map(l=>`<a href="${l.href}">${l.label}</a>`).join('')}
        </div>
      </div>` : '';
    return `
      <div class="wf-header">
        <a class="wf-brand" href="/">
          <img src="/static/logo32.png" alt="Wave Finder logo" width="26" height="26">
          <div class="wf-name">Wave Finder</div>
        </a>
        <div class="wf-spacer"></div>
        <nav class="wf-nav">
          ${linksPrimary.map(l=>pill(l.href,l.label,l.key)).join('')}
          ${more}
        </nav>
        <nav class="wf-nav-mobile">
          ${linksPrimary.map(l=>pill(l.href,l.label,l.key)).join('')}
          <button class="wf-burger" id="wf-burger" aria-label="Open menu">☰</button>
        </nav>
      </div>
      <div class="wf-drawer" id="wf-drawer">
        <div class="panel">
          <div class="brand">
            <img src="/static/logo32.png" alt="Wave Finder" width="24" height="24" />
            <div class="name">Wave Finder</div>
          </div>
          <div class="divider"></div>
          ${[...linksPrimary, ...linksMore].map(l=>`<a href="${l.href}">${l.label}</a>`).join('')}
        </div>
      </div>`;
  }
  function mount(){
    const mountPoint = document.getElementById('wf-header');
    if (!mountPoint) return;
    mountPoint.innerHTML = buildHeader();
    const moreBtn = document.getElementById('wf-more-btn');
    const moreMenu = document.getElementById('wf-more-menu');
    let header, burger, drawer;
    function openDrawer(){
      drawer.classList.add('open');
      header.classList.add('wf-header--hidden');
      document.body.style.overflow = 'hidden';
    }
    function closeDrawer(){
      drawer.classList.remove('open');
      header.classList.remove('wf-header--hidden');
      document.body.style.overflow = '';
    }
    if (moreBtn){
      moreBtn.addEventListener('click',(e)=>{
        const isSmall = window.matchMedia('(max-width: 768px)').matches;
        if (isSmall){
          e.preventDefault();
          openDrawer();
          return;
        }
        moreBtn.parentElement.classList.toggle('open');
      });
      document.addEventListener('click',(e)=>{
        if (!moreBtn.parentElement.contains(e.target)){
          moreBtn.parentElement.classList.remove('open');
        }
      });
    }
    burger = document.getElementById('wf-burger');
    drawer = document.getElementById('wf-drawer');
    header = mountPoint.querySelector('.wf-header');

    // Portal the drawer to <body> so it is fixed relative to the viewport,
    // not the transformed #wf-header container. This preserves header centering
    // via transform while ensuring the overlay covers the full screen.
    if (drawer && drawer.parentElement !== document.body){
      document.body.appendChild(drawer);
    }
    burger.addEventListener('click', openDrawer);
    drawer.addEventListener('click',(e)=>{ if (e.target===drawer) closeDrawer(); });
    // Close the drawer when clicking any link inside it
    drawer.querySelectorAll('a').forEach(a => a.addEventListener('click', closeDrawer));
  }
  window.addEventListener('DOMContentLoaded', mount);
})();
