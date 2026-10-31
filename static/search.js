/* منطق البحث والفلترة في المتصفح.
   - الدوال النقية قابلة للاختبار بـ Node.
   - init() يربط الصفحة: فلترة فورية محلياً مع توحيد البيانات وترتيب ذكي للنتائج. */
(function (root) {
  'use strict';

  // معالجة ذكية للنصوص
  function advancedNormalize(s) {
      let str = String(s).toLowerCase();
      // 1. الأرقام العربية للإنجليزية
      str = str.replace(/[٠-٩]/g, d => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)));
      // 2. معالجة الأرقام العشرية (0.50 -> 0.5)
      str = str.replace(/(\d+\.\d+)/g, match => parseFloat(match).toString());
      // 3. فصل الحروف عن الأرقام لضمان عدم اندماجها بشكل يمنع البحث المستقل
      // يحول "0.5m" إلى "0.5 m" ويحول "cat6" إلى "cat 6" لضمان مطابقة الـ Tokens بدقة
      str = str.replace(/([a-z])(\d)/g, '$1 $2');
      str = str.replace(/(\d)([a-z])/g, '$1 $2');
      return str;
  }

  function tokenize(q) {
    return advancedNormalize(q).split(/\s+/).filter(Boolean);
  }
  
  function hasArabic(q) { return /[\u0600-\u06FF]/.test(q); }

  function init() {
    const $ = id => document.getElementById(id);
    const input = $('searchInput'), tbody = $('productsTableBody');
    const counter = $('resultCount'), emptyState = $('emptyState'), approxNote = $('approxNote');
    const clearBtn = $('clearSearchBtn');

    const items = Array.from(tbody.querySelectorAll('tr')).filter(tr => !tr.classList.contains('separator-row')).map(tr => ({
      tr, id: tr.dataset.id, code: tr.dataset.code, brand: tr.dataset.brand,
      mainCat: tr.dataset.mainCat, subCat: tr.dataset.subCat,
      nameHay: tr.dataset.name + ' ' + tr.dataset.brand.toLowerCase(),
      catHay: tr.dataset.name + ' ' + tr.dataset.code,
    }));
    const byId = new Map(items.map(i => [i.id, i]));

    let brand = '', selectedMainCat = '', selectedSubCat = '';
    let smart = null;            
    let pending = false, seq = 0, timer = null, smartFailed = false;

    const searchType = () => {
        const el = document.querySelector('input[name="searchType"]:checked');
        return el ? el.value : 'name';
    };
    const smartEligible = q => searchType() === 'name' && hasArabic(q);

    function render() {
      const q = input.value.trim();
      const tokens = tokenize(q);
      const useSmart = smart && smart.query === q && tokens.length > 0;
      const type = searchType();
      
      if (clearBtn) clearBtn.style.display = q.length > 0 ? 'block' : 'none';

      const oldSeparator = document.getElementById('approxSeparator');
      if (oldSeparator) oldSeparator.remove();

      items.forEach(it => {
          it.tr.classList.add('hidden-row');
          if (it.tr.cells[1].dataset.orig) it.tr.cells[1].innerHTML = it.tr.cells[1].dataset.orig;
          if (it.tr.cells[0].dataset.orig) it.tr.cells[0].innerHTML = it.tr.cells[0].dataset.orig;
      });

      let filteredItems = items.filter(it => {
        if (brand && it.brand !== brand) return false;
        if (selectedMainCat && it.mainCat !== selectedMainCat) return false;
        if (selectedSubCat && it.subCat !== selectedSubCat) return false;
        return true;
      });

      const frag = document.createDocumentFragment();
      let shown = 0;

      function highlightAndAppend(list) {
          list.forEach(it => {
              it.tr.classList.remove('hidden-row');
              shown++;
              
              if (q.length > 0 && !useSmart) {
                  const codeCell = it.tr.cells[0]; 
                  const nameCell = it.tr.cells[1];
                  if (!nameCell.dataset.orig) nameCell.dataset.orig = nameCell.innerHTML;
                  if (!codeCell.dataset.orig) codeCell.dataset.orig = codeCell.innerHTML;
                  
                  // تظليل النص المطابق بناءً على ما كتبه المستخدم مباشرة (وليس الـ tokens المعالجة)
                  let rawTokens = q.toLowerCase().split(/\s+/).filter(Boolean);
                  let regexPattern = rawTokens.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
                  let regex = new RegExp(`(${regexPattern})`, 'gi');
                  
                  if (type === 'name') nameCell.innerHTML = nameCell.dataset.orig.replace(regex, '<span class="highlight">$1</span>');
                  else if (type === 'code') codeCell.innerHTML = codeCell.dataset.orig.replace(regex, '<span class="highlight">$1</span>');
              }
              frag.appendChild(it.tr);
          });
      }

      if (tokens.length === 0) {
          highlightAndAppend(filteredItems);
      } 
      else if (useSmart) {
          let smartFiltered = smart.ids.map(id => byId.get(String(id))).filter(it => it && filteredItems.includes(it));
          highlightAndAppend(smartFiltered);
      } 
      else {
          let matchedItems = [];

          for (const it of filteredItems) {
            let hay = type === 'code' ? advancedNormalize(it.code) : advancedNormalize(it.nameHay);
            let matchedTokens = 0;
            let score = 0;
            
            for (const t of tokens) { 
                if (hay.includes(t)) {
                    matchedTokens++;
                    let escapedToken = t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                    let exactWordRegex = new RegExp(`(?:^|\\s)${escapedToken}(?:\\s|$)`, 'i');
                    
                    if (exactWordRegex.test(hay)) {
                        score += 100; 
                    } else {
                        score += 10;  
                    }
                }
            }
            
            if (matchedTokens === tokens.length) {
                it.searchScore = score;
                matchedItems.push(it);
            }
          }
          
          matchedItems.sort((a, b) => b.searchScore - a.searchScore);
          highlightAndAppend(matchedItems);
      }

      tbody.appendChild(frag);

      if (counter) counter.textContent = pending ? 'جاري البحث…' : `عدد النتائج: ${shown} من ${items.length}`;
      if (approxNote) approxNote.classList.toggle('d-none', !(useSmart && smart && smart.approx && shown > 0));
      if (emptyState) emptyState.classList.toggle('d-none', pending || shown !== 0);
      const smartError = $('smartError');
      if (smartError) smartError.classList.toggle('d-none', !smartFailed);
    }

    function runSmart(q) {
      const mine = ++seq;
      pending = true; smartFailed = false; render();
      fetch('/search?type=name&q=' + encodeURIComponent(q))
        .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(d => {
          if (mine !== seq) return;               
          pending = false;
          smart = { query: q, ids: d.ids.map(String), approx: d.approx };
          render();
        })
        .catch(() => {
          if (mine !== seq) return;
          pending = false; smart = null; smartFailed = true; render();
        });
    }

    function onQueryChange() {
      clearTimeout(timer);
      seq++;                                       
      const q = input.value.trim();
      smartFailed = false;
      if (smartEligible(q)) {
        pending = true; render();
        timer = setTimeout(() => runSmart(q), 200);  
      } else {
        pending = false; smart = null; render();
      }
    }

    const subCatContainer = $('subCatContainer');
    const mainBtns = document.querySelectorAll('.main-cat-btn');
    const subWrappers = document.querySelectorAll('.sub-cat-wrapper');
    const subCards = document.querySelectorAll('.sub-category-card');

    mainBtns.forEach(btn => btn.addEventListener('click', () => {
      const wasActive = btn.classList.contains('btn-dark');
      mainBtns.forEach(b => { b.classList.remove('btn-dark'); b.classList.add('btn-outline-secondary'); });
      
      if (!wasActive) {
        btn.classList.remove('btn-outline-secondary');
        btn.classList.add('btn-dark');
        selectedMainCat = btn.dataset.mainCat;
        selectedSubCat = ''; 
        
        if (subCatContainer) subCatContainer.classList.remove('d-none');
        subWrappers.forEach(w => {
          w.classList.toggle('d-none', w.dataset.parent !== selectedMainCat);
        });
        subCards.forEach(c => c.classList.remove('active-category'));
      } else {
        selectedMainCat = '';
        selectedSubCat = '';
        if (subCatContainer) subCatContainer.classList.add('d-none');
      }
      render();
    }));

    subCards.forEach(card => card.addEventListener('click', () => {
      const wasActive = card.classList.contains('active-category');
      subCards.forEach(c => c.classList.remove('active-category'));
      
      if (!wasActive) {
        card.classList.add('active-category');
        selectedSubCat = card.dataset.subCat;
      } else {
        selectedSubCat = '';
      }
      render();
    }));

    function toggleExclusive(selector, activeClass, onChange) {
      document.querySelectorAll(selector).forEach(el => el.addEventListener('click', () => {
        const wasActive = el.classList.contains(activeClass);
        document.querySelectorAll(selector).forEach(x => x.classList.remove(activeClass));
        if (!wasActive) el.classList.add(activeClass);
        onChange(wasActive ? null : el);
        render();
      }));
    }
    toggleExclusive('.brand-box', 'active-brand', el => { brand = el ? el.dataset.brand : ''; });

    const moreBtn = $('toggleBrands'), moreBox = $('moreBrands');
    if (moreBtn && moreBox) {
        moreBtn.addEventListener('click', () => {
          const open = moreBox.classList.toggle('d-none') === false;
          moreBtn.textContent = open ? 'إخفاء' : moreBtn.dataset.label;
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            input.value = '';
            onQueryChange();
            input.focus();
        });
    }

    if (input) input.addEventListener('input', onQueryChange);
    document.querySelectorAll('input[name="searchType"]').forEach(r => r.addEventListener('change', onQueryChange));
    
    render();
  }

  const api = { advancedNormalize, tokenize, hasArabic, init };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EtqanSearch = api;
})(typeof window !== 'undefined' ? window : globalThis);