import test from 'node:test';
import assert from 'node:assert/strict';
import {navigationGroups,navigationGroup,isNavigationPage} from './navigation.ts';

test('four main destinations retain every existing page exactly once',()=>{
  assert.equal(navigationGroups.length,4);
  const routes=navigationGroups.flatMap(group=>group.links.map(([href])=>href));
  assert.equal(new Set(routes).size,16);
  for(const route of ['/','/memories','/documents','/knowledge','/timeline','/intelligence','/projects','/agent','/imports','/connectors','/approvals','/system','/observability','/disaster-recovery','/audit','/settings']){
    assert(routes.includes(route));assert(navigationGroup(route));
  }
});

test('direct and nested URLs select the correct containing section',()=>{
  assert.equal(navigationGroup('/memories/record-id').title,'Library');
  assert.equal(navigationGroup('/agent').title,'Workspace');
  assert.equal(navigationGroup('/connectors').title,'Capture & review');
  assert.equal(navigationGroup('/settings').title,'System');
  assert(isNavigationPage('/memories/record-id','/memories'));
  assert(!isNavigationPage('/memories-other','/memories'));
  assert(!isNavigationPage('/system','/'));
  assert.equal(navigationGroup('/missing-page'),undefined);
});
